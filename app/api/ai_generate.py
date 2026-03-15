"""
AI-powered ADR generation endpoints with validation, conflict detection, and review flow.
"""
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel

from app.core.security import User, require_scopes
from app.db.adr_store import create_adr as db_create, get_adr as db_get
from app.services.ai_generator import (
    ADRGenerationRequest,
    AIGenerationError,
    get_generator,
)
from app.services.adr_validator import validate_adr, llm_validate_adr, ADRValidationResult
from app.services.conflict_detector import detect_conflicts

router = APIRouter(prefix="/adrs", tags=["AI ADR Generation"])


class GenerateResponse(BaseModel):
    generated: bool
    adr: dict
    validation: Optional[dict] = None
    conflicts: list = []
    conflict_warning: Optional[str] = None
    rag_context_used: bool = False
    related_adrs: list = []
    model_used: str = ""
    profile: str = "detailed"
    review_required: bool = True
    message: str = ""
    warnings: list = []  # Non-blocking issues the user should know about


@router.post("/generate", response_model=GenerateResponse, status_code=status.HTTP_201_CREATED)
async def generate_adr(
    request: ADRGenerationRequest,
    user: User = Depends(require_scopes(["adr:write"]))
):
    """
    Generate an ADR with RAG context, quality validation, and conflict detection.
    Returns the ADR with validation score, conflicts, and review flag.
    """
    try:
        generator = get_generator()
        warnings = []

        # 1. Generate ADR
        generated, provenance = await generator.generate_async(request)

        # 2. Layer 1: Free heuristic validation
        validation = validate_adr(generated, constraints=request.constraints)

        # 3. Layer 2: If Layer 1 flags issues, use cheap LLM scoring
        if not validation.passed:
            llm_result = llm_validate_adr(generated, generator)
            validation.llm_validated = True
            validation.score = min(validation.score, llm_result.score)
            validation.passed = validation.score >= 7
            validation.suggestions.extend(llm_result.suggestions)

            # 4. Auto-retry if score < 7 (max 1 retry)
            if not validation.passed:
                feedback = "Issues found:\n" + "\n".join(validation.issues + validation.suggestions)
                generated, provenance = await generator.generate_async(request, feedback=feedback)
                validation = validate_adr(generated, constraints=request.constraints)
                validation.retried = True

        # 5. Conflict detection (free heuristic + optional cheap LLM) (retried ADR may have different text)
        conflicts = detect_conflicts(generated)
        conflict_warning = None
        if conflicts:
            conflict_warning = f"\u26a0 {len(conflicts)} potential conflict(s) with existing ADRs: " + \
                "; ".join(c.get("reason", "") for c in conflicts[:3])
            generated.conflicts = conflicts
            generated.conflict_warning = conflict_warning

        # 6. Store ALL sections in SQLite (including extended fields)
        adr = db_create(
            title=generated.title,
            context=generated.context,
            decision=generated.decision,
            consequences=generated.consequences,
            author=user.username,
            tags=generated.tags,
            ai_generated=True,
            ai_model=generator.model,
            y_statement=generated.y_statement,
            decision_drivers=generated.decision_drivers,
            alternatives_considered=generated.alternatives_considered,
            impact=generated.impact,
            reversibility=generated.reversibility,
            related_decisions=generated.related_decisions,
        )

        # 7. Index in ChromaDB
        idx_ok = _index_adr(adr)
        if not idx_ok:
            warnings.append("ADR saved but not indexed in search — ChromaDB may be unavailable")

        # 8. Response
        full_adr = dict(adr)

        return GenerateResponse(
            generated=True,
            adr=full_adr,
            validation=validation.model_dump(),
            conflicts=conflicts,
            conflict_warning=conflict_warning,
            rag_context_used=bool(provenance),
            related_adrs=provenance,
            model_used=generator.model,
            profile=request.profile,
            review_required=True,
            warnings=warnings,
            message="ADR generated. Review required before accepting."
        )

    except AIGenerationError as e:
        # Human-readable AI errors
        msg = str(e)
        if "API_KEY" in msg.upper() or "api_key" in msg:
            msg = "AI API key is not configured or invalid. Go to Settings to set your API key."
        elif "rate" in msg.lower() and "limit" in msg.lower():
            msg = "AI provider rate limit reached. Wait a moment and try again."
        elif "model" in msg.lower() and ("not found" in msg.lower() or "does not exist" in msg.lower()):
            msg = f"The configured AI model is not available. Check your model name in Settings."
        elif "connect" in msg.lower() or "timeout" in msg.lower():
            msg = "Could not reach the AI provider. Check your network connection and API base URL in Settings."
        raise HTTPException(status.HTTP_500_INTERNAL_SERVER_ERROR, detail=msg)
    except Exception as e:
        raise HTTPException(status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Something went wrong: {str(e)}")


@router.post("/generate/draft", response_model=GenerateResponse)
async def generate_adr_draft(
    request: ADRGenerationRequest,
    user: User = Depends(require_scopes(["adr:read", "adr:write"]))
):
    """Generate an ADR draft without saving. For preview before committing."""
    try:
        generator = get_generator()
        generated, provenance = await generator.generate_async(request)
        validation = validate_adr(generated, constraints=request.constraints)
        conflicts = detect_conflicts(generated)

        full_adr = {
            "id": f"draft-{datetime.utcnow().strftime('%H%M%S')}",
            "title": generated.title,
            "y_statement": generated.y_statement,
            "context": generated.context,
            "decision_drivers": generated.decision_drivers,
            "decision": generated.decision,
            "alternatives_considered": generated.alternatives_considered,
            "consequences": generated.consequences,
            "impact": generated.impact,
            "reversibility": generated.reversibility,
            "related_decisions": generated.related_decisions,
            "status": "Proposed",
            "tags": generated.tags,
            "author": user.username,
            "ai_generated": True,
            "ai_model": generator.model,
        }

        return GenerateResponse(
            generated=True,
            adr=full_adr,
            validation=validation.model_dump(),
            conflicts=conflicts,
            conflict_warning=f"⚠ {len(conflicts)} conflict(s)" if conflicts else None,
            model_used=generator.model,
            profile=request.profile,
            review_required=True,
            message="Draft generated. POST to /adrs to save."
        )

    except AIGenerationError as e:
        raise HTTPException(status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


def _index_adr(adr: dict) -> bool:
    """Index ADR in ChromaDB. Returns True on success, False on failure."""
    import logging
    logger = logging.getLogger(__name__)
    try:
        from app.services.embeddings import get_embedding_service
        from app.services.vector_store import get_vector_store, COLLECTION_ADRS
        vs = get_vector_store()
        if not vs:
            logger.warning(f"ChromaDB unavailable — ADR {adr['id']} not indexed")
            return False
        text = f"{adr['title']}\n{adr.get('context', '')}\n{adr.get('decision', '')}"
        embedding = get_embedding_service().embed(text)
        vs.upsert(COLLECTION_ADRS, adr["id"], embedding, text, {
            "title": adr["title"],
            "status": adr.get("status", "Proposed"),
        })
        return True
    except Exception as e:
        logger.warning(f"Failed to index ADR {adr['id']}: {e}")
        return False
