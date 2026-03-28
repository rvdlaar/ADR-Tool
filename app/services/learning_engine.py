"""
Learning engine — extracts reusable lessons from user corrections to AI-generated ADRs.
Compares AI output snapshots against accepted versions, categorizes changes, and stores
learnings for injection into future generations.
"""
import hashlib
import json
from difflib import SequenceMatcher

from app.db.adr_store import (
    create_learning,
    get_learning_by_hash,
    update_learning,
)

SECTIONS = [
    "context", "decision", "consequences", "impact",
    "alternatives_considered", "reversibility", "y_statement",
    "decision_drivers", "related_decisions",
]


def compute_section_diffs(generated_json: str, accepted: dict) -> list[dict]:
    """Compare AI output to user's accepted version, return changed sections."""
    try:
        generated = json.loads(generated_json)
    except (json.JSONDecodeError, TypeError):
        return []

    diffs = []
    for section in SECTIONS:
        ai_text = str(generated.get(section, "") or "")
        user_text = str(accepted.get(section, "") or "")
        if ai_text and user_text and ai_text != user_text:
            ratio = SequenceMatcher(None, ai_text, user_text).ratio()
            if ratio < 0.95:  # >5% change = meaningful edit
                diffs.append({
                    "section": section,
                    "ai_text": ai_text,
                    "user_text": user_text,
                    "similarity": ratio,
                    "change_size": abs(len(user_text) - len(ai_text)),
                })
    return diffs


def extract_learnings(adr_id: str, diffs: list[dict], snapshot: dict):
    """From section diffs, extract reusable lessons and store them."""
    for diff in diffs:
        # Confidence based on edit magnitude
        sim = diff["similarity"]
        if sim > 0.8:
            confidence = 0.3
        elif sim > 0.5:
            confidence = 0.5
        else:
            confidence = 0.7

        category = categorize_change(diff["section"], diff["ai_text"], diff["user_text"])
        lesson = generate_lesson_heuristic(diff)

        # Dedup via hash
        lesson_hash = hashlib.sha256(lesson.encode()).hexdigest()[:12]
        existing = get_learning_by_hash(lesson_hash)
        if existing:
            # Boost confidence of existing learning
            new_confidence = min(0.95, existing["confidence"] + 0.1)
            update_learning(existing["id"], confidence=new_confidence)
        else:
            create_learning(
                adr_id=adr_id,
                category=category,
                lesson=lesson,
                section=diff["section"],
                what_ai_generated=diff["ai_text"][:2000],
                what_user_wrote=diff["user_text"][:2000],
                confidence=confidence,
                hash_val=lesson_hash,
            )


def categorize_change(section: str, ai_text: str, user_text: str) -> str:
    """Heuristic categorization of what kind of correction this is."""
    len_ratio = len(user_text) / max(len(ai_text), 1)
    if len_ratio < 0.5:
        return "scope"       # User significantly shortened (too verbose)
    if len_ratio > 2.0:
        return "content"     # User significantly expanded (too shallow)
    if section in ("impact", "alternatives_considered"):
        return "structure"   # Structural sections often get reformatted
    return "style"           # Default: style/wording preference


def generate_lesson_heuristic(diff: dict) -> str:
    """Simple pattern-based lesson extraction."""
    section = diff["section"]
    sim = diff["similarity"]
    ai_len = len(diff["ai_text"])
    user_len = len(diff["user_text"])

    if user_len < ai_len * 0.5:
        return f"In {section}: be more concise. User shortened from {ai_len} to {user_len} chars."
    if user_len > ai_len * 2:
        return f"In {section}: provide more depth. User expanded from {ai_len} to {user_len} chars."
    if sim < 0.5:
        return f"In {section}: user rewrote substantially ({int(sim * 100)}% similarity). The AI approach was off-target."
    return f"In {section}: user refined wording ({int(sim * 100)}% similarity). Minor style adjustment."
