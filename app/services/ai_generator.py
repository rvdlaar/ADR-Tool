"""
AI-powered ADR Generation Service.
Hybrid format: Nygard base + Y-statement + Impact section.
RAG-augmented with conflict detection and quality validation.
"""
import json
import os
import re
from typing import Optional, Dict, Any, List
from datetime import datetime

from openai import OpenAI
from pydantic import BaseModel


# =============================================================================
# Models
# =============================================================================

class ADRGenerationRequest(BaseModel):
    """Request to generate an ADR using AI"""
    title: str
    description: str
    context: Optional[str] = None
    requirements: Optional[List[str]] = None
    constraints: Optional[List[str]] = None
    alternatives: Optional[List[str]] = None
    # Extended fields
    decision_drivers: Optional[List[str]] = None
    impacted_roles: Optional[List[str]] = None
    success_criteria: Optional[List[str]] = None
    timeline: Optional[str] = None
    scope: Optional[str] = None
    profile: str = "detailed"  # "detailed" or "guided"


class GeneratedADR(BaseModel):
    """AI-generated ADR content"""
    title: str
    y_statement: str = ""
    context: str
    decision_drivers: str = ""
    decision: str
    alternatives_considered: str = ""
    consequences: str
    impact: str = ""
    reversibility: str = ""
    related_decisions: str = ""
    status: str = "Proposed"
    tags: List[str] = []
    metadata: Dict[str, Any] = {}
    # Quality fields
    conflicts: Optional[List[dict]] = None
    conflict_warning: Optional[str] = None


class AIGenerationError(Exception):
    """Error during AI generation"""
    pass


# =============================================================================
# Prompt Templates
# =============================================================================

SYSTEM_PROMPT = """You are an expert software architect who produces exceptional Architecture Decision Records.

CRITICAL RULES:
- Never use vague adjectives without metrics. Instead of "better performance", write "40% reduction in P95 latency based on benchmark X" or "estimated 2x throughput improvement (to be validated)".
- If you don't know a specific metric, say "estimated" or "to be validated" — never fabricate numbers.
- Every consequence must answer: "So what? What does this mean for someone building on top of this decision?"
- The Impact section must name specific roles and describe concrete actions they need to take.
- Alternatives must include a comparison with specific evaluation criteria, not just pros/cons lists.

Generate the ADR as a JSON object."""

ADR_PROMPT_DETAILED = """Generate a comprehensive Architecture Decision Record.

## Required Output Structure (JSON)

{{
    "title": "[Number]. [Descriptive Title]",
    "y_statement": "In the context of [situation], facing [problem], we decided [decision] to achieve [goal], accepting [trade-off].",
    "context": "### Context\\n- What situation prompted this decision?\\n- What specific forces are at play? (technical constraints, business requirements, team capabilities)\\n- What assumptions are we making? (list each explicitly)",
    "decision_drivers": "### Decision Drivers\\n- [Driver]: Why this is happening NOW\\n- [Driver]: What triggered the need",
    "decision": "### Decision\\n[The specific change and why it's the right call]",
    "alternatives_considered": "### Alternatives Considered\\n| Option | Pros | Cons | Why rejected |\\n|--------|------|------|-------------|\\n| ... | ... | ... | ... |",
    "consequences": "### Consequences\\n**Positive:**\\n- [Specific, measurable outcome]\\n\\n**Negative:**\\n- [Specific cost or limitation]\\n\\n**Risks:**\\n- [What could go wrong, likelihood, mitigation]",
    "impact": "### Impact\\n| Role | Impact | Why | Action needed |\\n|------|--------|-----|--------------|\\n| ... | ... | ... | ... |",
    "reversibility": "### Reversibility\\n- Can this be reversed? At what cost?\\n- Point of no return\\n- Rollback plan",
    "related_decisions": "### Related Decisions\\n- Supersedes: [if applicable]\\n- Depends on: [if applicable]",
    "tags": ["tag1", "tag2"],
    "metadata": {{"ai_generated": true, "generation_date": "{date}", "model_used": "{model}", "profile": "detailed"}}
}}

## Input Information

Title: {title}
Description: {description}
{context_section}
{requirements_section}
{constraints_section}
{alternatives_section}
{drivers_section}
{roles_section}
{criteria_section}
{timeline_section}
{scope_section}

{rag_context}"""

ADR_PROMPT_GUIDED = """Generate an Architecture Decision Record with extra guidance for the reader.

For each section, include brief explanatory notes about what makes a good entry.

## Required Output Structure (JSON)

{{
    "title": "[Number]. [Descriptive Title]",
    "y_statement": "In the context of [situation], facing [problem], we decided [decision] to achieve [goal], accepting [trade-off]. (This one-liner should capture the essence of the entire ADR.)",
    "context": "### Context\\n[Describe the situation. Be specific about:\\n- The problem you're solving\\n- Technical and business constraints\\n- Assumptions you're making (these often become the first things to revisit)]",
    "decision_drivers": "### Decision Drivers\\n[Why is this decision happening NOW? Common drivers: tech debt reaching critical mass, new compliance requirement, team scaling, performance SLA breach]",
    "decision": "### Decision\\n[State the decision clearly. A good decision is one where someone reading it 6 months from now understands exactly what changed and why.]",
    "alternatives_considered": "### Alternatives Considered\\n| Option | Pros | Cons | Why rejected |\\n|--------|------|------|-------------|\\n| [Name] | [Be specific] | [Be specific] | [The real reason, not 'it was complex'] |",
    "consequences": "### Consequences\\n**Positive:**\\n- [What gets better? Include metrics where possible.]\\n\\n**Negative:**\\n- [What gets harder? Be honest — every decision has costs.]\\n\\n**Risks:**\\n- [What could go wrong? How likely? What's the mitigation?]",
    "impact": "### Impact\\n| Role | Impact | Why | Action needed |\\n|------|--------|-----|--------------|\\n| [e.g. Frontend team] | [What changes for them] | [Why they care] | [What they need to do] |",
    "reversibility": "### Reversibility\\n[Can you undo this? At what cost? When is the point of no return? What's the rollback plan if this fails?]",
    "related_decisions": "### Related Decisions\\n[Link to other ADRs this depends on or supersedes.]",
    "tags": ["tag1", "tag2"],
    "metadata": {{"ai_generated": true, "generation_date": "{date}", "model_used": "{model}", "profile": "guided"}}
}}

## Input Information

Title: {title}
Description: {description}
{context_section}
{requirements_section}
{constraints_section}
{alternatives_section}
{drivers_section}
{roles_section}
{criteria_section}
{timeline_section}
{scope_section}

{rag_context}"""


# =============================================================================
# Service
# =============================================================================

class ADRGenerator:
    def __init__(self):
        self.provider = os.getenv("AI_PROVIDER", "openai").lower()
        self.api_key = os.getenv("AI_API_KEY", "")
        self.model = os.getenv("AI_MODEL", "gpt-4o-mini")
        self.base_url = os.getenv("AI_BASE_URL", "")

        client_kwargs = {"api_key": self.api_key}
        if self.base_url:
            client_kwargs["base_url"] = self.base_url
        self.client = OpenAI(**client_kwargs)

    def _build_prompt(self, request: ADRGenerationRequest, rag_context: str = "") -> str:
        template = ADR_PROMPT_GUIDED if request.profile == "guided" else ADR_PROMPT_DETAILED

        sections = {
            "context_section": f"Additional Context: {request.context}" if request.context else "",
            "requirements_section": ("Requirements:\n" + "\n".join(f"- {r}" for r in request.requirements)) if request.requirements else "",
            "constraints_section": ("Constraints:\n" + "\n".join(f"- {c}" for c in request.constraints)) if request.constraints else "",
            "alternatives_section": ("Alternatives to Consider:\n" + "\n".join(f"- {a}" for a in request.alternatives)) if request.alternatives else "",
            "drivers_section": ("Decision Drivers:\n" + "\n".join(f"- {d}" for d in request.decision_drivers)) if request.decision_drivers else "",
            "roles_section": ("Impacted Roles:\n" + "\n".join(f"- {r}" for r in request.impacted_roles)) if request.impacted_roles else "",
            "criteria_section": ("Success Criteria:\n" + "\n".join(f"- {c}" for c in request.success_criteria)) if request.success_criteria else "",
            "timeline_section": f"Timeline/Reversibility Window: {request.timeline}" if request.timeline else "",
            "scope_section": f"Scope: {request.scope}" if request.scope else "",
            "rag_context": rag_context,
            "title": request.title,
            "description": request.description,
            "date": datetime.utcnow().isoformat(),
            "model": self.model,
        }

        return template.format(**sections)

    def _parse_response(self, content: str) -> GeneratedADR:
        try:
            json_start = content.find("{")
            json_end = content.rfind("}") + 1
            if json_start >= 0 and json_end > json_start:
                data = json.loads(content[json_start:json_end])
            else:
                data = json.loads(content)
            return GeneratedADR(**data)
        except json.JSONDecodeError as e:
            raise AIGenerationError(f"Failed to parse AI response: {e}\nResponse: {content[:500]}")

    def _retrieve_rag_context(self, request: ADRGenerationRequest) -> str:
        """Retrieve related ADRs and context docs. Returns structured context."""
        try:
            from app.services.embeddings import get_embedding_service
            from app.services.vector_store import get_vector_store, COLLECTION_ADRS, COLLECTION_CONTEXT

            vs = get_vector_store()
            if not vs:
                return ""

            query_text = f"{request.title}\n{request.description}"
            embedding = get_embedding_service().embed(query_text)
            sections = []

            # Top 3 related ADRs — 2000 chars each (not 500)
            adr_hits = vs.search(COLLECTION_ADRS, embedding, limit=3)
            if adr_hits:
                adr_parts = []
                for h in adr_hits:
                    doc = h.get("document", "")[:2000]
                    adr_parts.append(f"**Related Decision (similarity: {h.get('score', 0):.2f}):**\n{doc}")
                sections.append("## Related Existing Decisions\n\n" + "\n\n".join(adr_parts))

            # Top 2 context docs — 2000 chars each
            doc_hits = vs.search(COLLECTION_CONTEXT, embedding, limit=2)
            if doc_hits:
                doc_parts = []
                for h in doc_hits:
                    doc = h.get("document", "")[:2000]
                    doc_parts.append(f"**Context Document:**\n{doc}")
                sections.append("## Relevant Context Documents\n\n" + "\n\n".join(doc_parts))

            if sections:
                return "\n\n".join(sections) + "\n\nConsider these when making your decision. If any related decision conflicts with your recommendation, flag it in the Related Decisions section.\n"
            return ""
        except Exception:
            return ""

    def generate(self, request: ADRGenerationRequest, feedback: str = "") -> GeneratedADR:
        """Generate an ADR with RAG context. Optionally include validator feedback for retry."""
        if not self.api_key:
            raise AIGenerationError("AI_API_KEY not configured.")

        rag_context = self._retrieve_rag_context(request)
        prompt = self._build_prompt(request, rag_context)

        if feedback:
            prompt += f"\n\n## Validator Feedback (improve these areas):\n{feedback}"

        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.7,
                max_tokens=3000,
                response_format={"type": "json_object"}
            )
            content = response.choices[0].message.content
            return self._parse_response(content)
        except AIGenerationError:
            raise
        except Exception as e:
            raise AIGenerationError(f"AI generation failed: {str(e)}")

    async def generate_async(self, request: ADRGenerationRequest, feedback: str = "") -> GeneratedADR:
        import asyncio
        return await asyncio.to_thread(self.generate, request, feedback)


_generator: Optional[ADRGenerator] = None

def get_generator() -> ADRGenerator:
    global _generator
    if _generator is None:
        _generator = ADRGenerator()
    return _generator
