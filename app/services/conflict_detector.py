"""
Conflict detection — checks if a new ADR contradicts existing decisions.
Cost-rightized: heuristic keyword check first (free), LLM only if flagged.
"""
import os
import re
import logging
from typing import List, Optional

logger = logging.getLogger(__name__)

# Opposing term pairs for heuristic conflict detection
OPPOSING_PAIRS = [
    ("rest", "grpc"), ("rest", "graphql"), ("grpc", "graphql"),
    ("postgresql", "mysql"), ("postgres", "mysql"), ("postgresql", "mongodb"),
    ("mongodb", "postgresql"), ("sql", "nosql"),
    ("monolith", "microservice"), ("monolithic", "microservices"),
    ("synchronous", "asynchronous"), ("sync", "async"),
    ("serverless", "container"), ("lambda", "kubernetes"),
    ("kubernetes", "ecs"), ("docker", "serverless"),
    ("react", "vue"), ("react", "angular"), ("vue", "angular"),
    ("jwt", "session"), ("oauth", "api-key"),
    ("aws", "gcp"), ("aws", "azure"), ("gcp", "azure"),
    ("redis", "memcached"),
    ("kafka", "rabbitmq"), ("kafka", "sqs"),
]


def detect_conflicts(generated_adr, embedding=None) -> List[dict]:
    """
    Detect potential conflicts between generated ADR and existing ADRs.

    1. Embed decision text (reuses embedding if provided)
    2. Search ChromaDB for high-similarity matches (> 0.85)
    3. Heuristic keyword check for opposing terms (FREE)
    4. LLM conflict check only if heuristic flags something (~$0.001)

    Returns list of conflict dicts: [{adr_id, title, reason, confidence}]
    """
    try:
        from app.services.embeddings import get_embedding_service
        from app.services.vector_store import get_vector_store, COLLECTION_ADRS

        vs = get_vector_store()
        if not vs:
            return []

        # Get embedding for the new ADR's decision
        decision_text = f"{generated_adr.title}\n{getattr(generated_adr, 'decision', '')}"
        if not embedding:
            embedding = get_embedding_service().embed(decision_text)

        # Search for highly similar existing ADRs
        hits = vs.search(COLLECTION_ADRS, embedding, limit=5)
        high_similarity = [h for h in hits if h.get("score", 0) > 0.80]

        if not high_similarity:
            return []

        conflicts = []
        new_text = decision_text.lower()

        for hit in high_similarity:
            existing_text = (hit.get("document", "") or "").lower()
            existing_title = hit.get("metadata", {}).get("title", hit.get("id", ""))

            # Heuristic: check for opposing terms
            conflict_reason = _heuristic_conflict_check(new_text, existing_text)

            if conflict_reason:
                # Optionally confirm with LLM (cheap)
                llm_reason = _llm_conflict_check(decision_text, hit.get("document", ""), existing_title)
                if llm_reason:
                    conflicts.append({
                        "adr_id": hit["id"],
                        "title": existing_title,
                        "reason": llm_reason,
                        "confidence": "high",
                        "similarity": hit.get("score", 0),
                    })
                else:
                    conflicts.append({
                        "adr_id": hit["id"],
                        "title": existing_title,
                        "reason": conflict_reason,
                        "confidence": "medium",
                        "similarity": hit.get("score", 0),
                    })

        return conflicts

    except Exception as e:
        logger.warning(f"Conflict detection failed: {e}")
        return []


def _heuristic_conflict_check(new_text: str, existing_text: str) -> Optional[str]:
    """Free heuristic: check if the two texts mention opposing technologies/approaches."""
    for term_a, term_b in OPPOSING_PAIRS:
        new_has_a = term_a in new_text
        new_has_b = term_b in new_text
        existing_has_a = term_a in existing_text
        existing_has_b = term_b in existing_text

        # New ADR uses A, existing uses B (or vice versa)
        if (new_has_a and existing_has_b and not existing_has_a) or \
           (new_has_b and existing_has_a and not existing_has_b):
            return f"Potential conflict: new ADR references '{term_a if new_has_a else term_b}' while existing ADR uses '{term_b if new_has_a else term_a}'"

    return None


def _llm_conflict_check(new_decision: str, existing_decision: str, existing_title: str) -> Optional[str]:
    """Cheap LLM check (~$0.001) — reuses the generator's OpenAI client."""
    try:
        from app.services.ai_generator import get_generator
        generator = get_generator()
        if not generator.api_key:
            return None
        client = generator.client

        prompt = f"""Do these two architecture decisions conflict? Answer with JSON: {{"conflicts": true/false, "reason": "one line explanation"}}

Decision A (NEW):
{new_decision[:500]}

Decision B (EXISTING: {existing_title}):
{existing_decision[:500]}"""

        response = client.chat.completions.create(
            model=generator.model,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.1,
            max_tokens=100,
            response_format={"type": "json_object"}
        )

        import json
        result = json.loads(response.choices[0].message.content)
        if result.get("conflicts"):
            return result.get("reason", "Conflicting decisions detected")
        return None

    except Exception:
        return None
