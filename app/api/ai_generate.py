"""
AI-powered ADR generation endpoints.
"""
import uuid
from datetime import datetime
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, status

from app.core.security import User, require_scopes
from app.models.adr import ADR, ADRStatus
from app.schemas.adr import ADRGenerateRequest, ADRGenerateResponse
from app.services.ai_generator import (
    ADRGenerator,
    ADRGenerationRequest,
    AIGenerationError,
    get_generator,
)

router = APIRouter(prefix="/adrs", tags=["AI ADR Generation"])


@router.post("/generate", response_model=ADRGenerateResponse, status_code=status.HTTP_201_CREATED)
async def generate_adr(
    request: ADRGenerateRequest,
    user: User = Depends(require_scopes(["adr:write"]))
):
    """
    Generate an ADR using AI.
    
    Provide a title and description, and the AI will generate a complete
    Architecture Decision Record with context, decision, and consequences.
    
    Requires adr:write scope.
    """
    try:
        generator = get_generator()
        
        # Build the generation request
        ai_request = ADRGenerationRequest(
            title=request.title,
            description=request.description,
            context=request.context,
            requirements=request.requirements,
            constraints=request.constraints,
            alternatives=request.alternatives,
        )
        
        # Generate the ADR
        generated = await generator.generate_async(ai_request)
        
        # Create full ADR in the database
        adr_id = str(uuid.uuid4())[:8]
        
        adr = ADR(
            id=adr_id,
            title=generated.title,
            context=generated.context,
            decision=generated.decision,
            consequences=generated.consequences,
            author=user.username,
            tags=generated.tags,
            status=ADRStatus.PROPOSED,
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow(),
            ai_generated=True,
            ai_model=generator.model,
        )
        
        # Store in the database (in-memory for now)
        from app.api.adrs import _adrs_db
        _adrs_db[adr_id] = adr
        
        return ADRGenerateResponse(
            generated=True,
            adr=adr.model_dump(),
            model_used=generator.model,
            message="ADR generated successfully"
        )
        
    except AIGenerationError as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to generate ADR: {str(e)}"
        )


@router.post("/generate/draft", response_model=ADRGenerateResponse)
async def generate_adr_draft(
    request: ADRGenerateRequest,
    user: User = Depends(require_scopes(["adr:read", "adr:write"]))
):
    """
    Generate an ADR draft without saving to database.
    
    Returns the generated ADR content for review before saving.
    Useful for previewing the AI output before creating the ADR.
    
    Requires adr:read and adr:write scopes.
    """
    try:
        generator = get_generator()
        
        ai_request = ADRGenerationRequest(
            title=request.title,
            description=request.description,
            context=request.context,
            requirements=request.requirements,
            constraints=request.constraints,
            alternatives=request.alternatives,
        )
        
        generated = await generator.generate_async(ai_request)
        
        # Create draft ADR (not saved to DB)
        adr_id = f"draft-{uuid.uuid4().hex[:8]}"
        
        adr = ADR(
            id=adr_id,
            title=generated.title,
            context=generated.context,
            decision=generated.decision,
            consequences=generated.consequences,
            author=user.username,
            tags=generated.tags,
            status=ADRStatus.PROPOSED,
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow(),
            ai_generated=True,
            ai_model=generator.model,
        )
        
        return ADRGenerateResponse(
            generated=True,
            adr=adr.model_dump(),
            model_used=generator.model,
            message="Draft ADR generated. POST to /adrs to save."
        )
        
    except AIGenerationError as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to generate draft: {str(e)}"
        )
