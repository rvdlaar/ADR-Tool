"""
ADR quality validator — cost-rightized with free heuristics first, cheap LLM scoring only when needed.
"""
import re
import os
from typing import List, Optional
from pydantic import BaseModel


class ADRValidationResult(BaseModel):
    score: int = 0                        # 1-10
    passed: bool = False                  # score >= 7
    issues: List[str] = []               # Specific problems
    suggestions: List[str] = []          # Improvements
    vague_terms_found: List[str] = []    # Terms needing metrics
    constraints_respected: bool = True
    retried: bool = False
    llm_validated: bool = False


# Vague terms that should have metrics nearby
VAGUE_TERMS = [
    r"\bbetter\b", r"\bimproved\b", r"\beasier\b", r"\bmore complex\b",
    r"\bmore powerful\b", r"\bfaster\b", r"\bslower\b", r"\bsimpler\b",
    r"\bmore secure\b", r"\bless secure\b", r"\bmore scalable\b",
    r"\bmore reliable\b", r"\bmore efficient\b", r"\bmore flexible\b",
]

# Patterns indicating a metric is nearby (within 50 chars)
METRIC_PATTERNS = [
    r"\d+%", r"\d+x", r"\d+ms", r"\d+s\b", r"\$\d+", r"\d+MB", r"\d+GB",
    r"\d+\s*req", r"\d+\s*RPS", r"estimated", r"to be validated", r"benchmark",
    r"measured", r"SLA", r"P\d+", r"latency", r"\d+\s*hour", r"\d+\s*day",
]


def validate_adr(generated_adr, constraints: Optional[List[str]] = None) -> ADRValidationResult:
    """
    Layer 1: Free heuristic validation. No LLM calls.
    Returns a validation result with issues and a heuristic score.
    """
    issues = []
    suggestions = []
    vague_found = []
    score = 10  # Start perfect, deduct for issues

    # Combine all text fields for analysis
    all_text = " ".join([
        getattr(generated_adr, "context", "") or "",
        getattr(generated_adr, "decision", "") or "",
        getattr(generated_adr, "consequences", "") or "",
        getattr(generated_adr, "impact", "") or "",
        getattr(generated_adr, "reversibility", "") or "",
        getattr(generated_adr, "alternatives_considered", "") or "",
        getattr(generated_adr, "y_statement", "") or "",
        getattr(generated_adr, "decision_drivers", "") or "",
    ])

    # --- Structure checks ---
    required_sections = {
        "context": getattr(generated_adr, "context", ""),
        "decision": getattr(generated_adr, "decision", ""),
        "consequences": getattr(generated_adr, "consequences", ""),
    }
    for section, content in required_sections.items():
        if not content or len(content.strip()) < 20:
            issues.append(f"Section '{section}' is missing or too short (< 20 chars)")
            score -= 2

    # Y-statement check
    y_stmt = getattr(generated_adr, "y_statement", "") or ""
    if len(y_stmt) < 20:
        issues.append("Y-statement is missing or too short")
        score -= 1

    # Impact section check
    impact = getattr(generated_adr, "impact", "") or ""
    if len(impact) < 20:
        issues.append("Impact section is missing — who is affected by this decision?")
        suggestions.append("Add an Impact table: | Role | Impact | Why | Action needed |")
        score -= 1
    elif "|" not in impact:
        suggestions.append("Impact section should use a table format for clarity")

    # Alternatives check
    alts = getattr(generated_adr, "alternatives_considered", "") or ""
    if len(alts) < 20:
        issues.append("Alternatives section is missing — what options were evaluated?")
        score -= 1
    elif "|" not in alts:
        suggestions.append("Alternatives should use a comparison table: | Option | Pros | Cons | Why rejected |")

    # Reversibility check
    rev = getattr(generated_adr, "reversibility", "") or ""
    if len(rev) < 10:
        suggestions.append("Add reversibility analysis: Can this be reversed? At what cost?")

    # --- Specificity checks ---
    consequences = getattr(generated_adr, "consequences", "") or ""
    if len(consequences) < 50:
        issues.append("Consequences are too shallow (< 50 chars)")
        score -= 1
    elif len(consequences) > 3000:
        suggestions.append("Consequences are very long (> 3000 chars) — consider being more concise")

    # Vague terms — only check decision/consequences/impact (not context, where vagueness is descriptive)
    actionable_text = " ".join([
        getattr(generated_adr, "decision", "") or "",
        getattr(generated_adr, "consequences", "") or "",
        getattr(generated_adr, "impact", "") or "",
        getattr(generated_adr, "alternatives_considered", "") or "",
    ])
    for pattern in VAGUE_TERMS:
        matches = list(re.finditer(pattern, actionable_text, re.IGNORECASE))
        for match in matches:
            start = max(0, match.start() - 50)
            end = min(len(actionable_text), match.end() + 50)
            context_window = actionable_text[start:end]
            has_metric = any(re.search(mp, context_window, re.IGNORECASE) for mp in METRIC_PATTERNS)
            if not has_metric:
                term = match.group()
                if term not in vague_found:
                    vague_found.append(term)

    if vague_found:
        issues.append(f"Vague terms without metrics: {', '.join(vague_found[:5])}")
        suggestions.append("Replace vague adjectives with specific measurements or add 'estimated'/'to be validated'")
        score -= min(len(vague_found), 3)  # Max -3 for vagueness

    # --- Constraint compliance ---
    constraints_ok = True
    if constraints:
        for constraint in constraints:
            # Simple string presence check
            constraint_lower = constraint.lower()
            keywords = [w for w in constraint_lower.split() if len(w) > 3]
            found = any(kw in all_text.lower() for kw in keywords)
            if not found:
                issues.append(f"Constraint may not be addressed: '{constraint}'")
                constraints_ok = False
                score -= 1

    # Clamp score
    score = max(1, min(10, score))

    return ADRValidationResult(
        score=score,
        passed=score >= 7,
        issues=issues,
        suggestions=suggestions,
        vague_terms_found=vague_found,
        constraints_respected=constraints_ok,
        retried=False,
        llm_validated=False,
    )


def llm_validate_adr(generated_adr, generator) -> ADRValidationResult:
    """
    Layer 2: Cheap LLM validation. Only called when Layer 1 flags issues.
    Uses the same model (gpt-4o-mini) with a compact prompt.
    """
    all_text = " ".join([
        getattr(generated_adr, "y_statement", "") or "",
        getattr(generated_adr, "context", "") or "",
        getattr(generated_adr, "decision", "") or "",
        getattr(generated_adr, "consequences", "") or "",
        getattr(generated_adr, "impact", "") or "",
    ])[:3000]

    prompt = f"""Rate this Architecture Decision Record 1-10 on specificity, actionability, and completeness.
List max 3 specific improvements. Respond in JSON: {{"score": N, "improvements": ["...", "..."]}}

ADR content:
{all_text}"""

    try:
        response = generator.client.chat.completions.create(
            model=generator.model,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.3,
            max_tokens=200,
            response_format={"type": "json_object"}
        )
        import json
        result = json.loads(response.choices[0].message.content)
        score = int(result.get("score", 5))
        improvements = result.get("improvements", [])

        return ADRValidationResult(
            score=score,
            passed=score >= 7,
            issues=[],
            suggestions=improvements[:3],
            vague_terms_found=[],
            constraints_respected=True,
            retried=False,
            llm_validated=True,
        )
    except Exception:
        # If LLM validation fails, return a neutral result
        return ADRValidationResult(score=6, passed=False, llm_validated=False)
