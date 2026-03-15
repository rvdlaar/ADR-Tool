"""
AI-powered ADR Generation Service.
Uses LLM to automatically generate Architecture Decision Records.
"""
import json
import os
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


class GeneratedADR(BaseModel):
    """AI-generated ADR content"""
    title: str
    context: str
    decision: str
    consequences: str
    status: str = "Proposed"
    tags: List[str] = []
    metadata: Dict[str, Any] = {}


class AIGenerationError(Exception):
    """Error during AI generation"""
    pass


# =============================================================================
# ADR Generation Prompt Template
# =============================================================================

ADR_GENERATION_PROMPT = """You are an expert software architect specializing in Architecture Decision Records (ADRs).
Your task is to generate a comprehensive ADR based on the provided information.

## ADR Format (MADR - Markdown Any Decision Records)

### Title
A short, descriptive title in the format: "{number}. {Title}"

### Context
The situation that prompted this decision. Include:
- What is the issue motivating this decision?
- What constraints must be met?
- What assumptions are we making?

### Decision
The change that we're proposing and/or doing. Include:
- What is the decision?
- Why is this the right decision?
- What alternatives were considered?

### Consequences
What becomes easier or more difficult to do because of this change. Include:
- Positive outcomes
- Negative outcomes
- Trade-offs

## Input Information

Title: {title}
Description: {description}
{context_section}
{requirements_section}
{constraints_section}
{alternatives_section}

## Output Format

Generate a complete ADR in the following JSON format:
{{
    "title": "1. [Descriptive Title]",
    "context": "Detailed context...",
    "decision": "Detailed decision...",
    "consequences": "Detailed consequences...",
    "tags": ["tag1", "tag2", "tag3"],
    "metadata": {{
        "ai_generated": true,
        "generation_date": "{date}",
        "model_used": "{model}"
    }}
}}

Ensure the ADR is:
1. Specific and actionable
2. Includes clear rationale
3. Lists consequences (positive and negative)
4. Has appropriate tags for categorization
"""


# =============================================================================
# Service
# =============================================================================

class ADRGenerator:
    """
    AI-powered ADR generator using LLM.
    Supports OpenAI and compatible APIs (OpenRouter, Ollama, etc.)
    """
    
    def __init__(self):
        self.provider = os.getenv("AI_PROVIDER", "openai").lower()
        self.api_key = os.getenv("AI_API_KEY", "")
        self.model = os.getenv("AI_MODEL", "gpt-4o-mini")
        self.base_url = os.getenv("AI_BASE_URL", "")
        
        # Initialize the client
        client_kwargs = {
            "api_key": self.api_key,
        }
        
        # Add base URL for alternative providers
        if self.base_url:
            client_kwargs["base_url"] = self.base_url
        
        self.client = OpenAI(**client_kwargs)
    
    def _build_prompt(self, request: ADRGenerationRequest) -> str:
        """Build the prompt from the request"""
        
        # Build optional sections
        context_section = f"Additional Context: {request.context}" if request.context else ""
        
        requirements_section = ""
        if request.requirements:
            requirements_section = "Requirements:\n" + "\n".join(f"- {r}" for r in request.requirements)
        
        constraints_section = ""
        if request.constraints:
            constraints_section = "Constraints:\n" + "\n".join(f"- {c}" for c in request.constraints)
        
        alternatives_section = ""
        if request.alternatives:
            alternatives_section = "Alternatives Considered:\n" + "\n".join(f"- {a}" for a in request.alternatives)
        
        return ADR_GENERATION_PROMPT.format(
            title=request.title,
            description=request.description,
            context_section=context_section,
            requirements_section=requirements_section,
            constraints_section=constraints_section,
            alternatives_section=alternatives_section,
            date=datetime.utcnow().isoformat(),
            model=self.model
        )
    
    def _parse_response(self, content: str) -> GeneratedADR:
        """Parse the LLM response into a GeneratedADR object"""
        
        # Extract JSON from the response
        try:
            # Try to find JSON in the response
            json_start = content.find("{")
            json_end = content.rfind("}") + 1
            
            if json_start >= 0 and json_end > json_start:
                json_str = content[json_start:json_end]
                data = json.loads(json_str)
            else:
                # Try parsing the whole response
                data = json.loads(content)
            
            return GeneratedADR(**data)
            
        except json.JSONDecodeError as e:
            raise AIGenerationError(f"Failed to parse AI response as JSON: {e}\nResponse: {content[:500]}")
    
    def _retrieve_rag_context(self, request: ADRGenerationRequest) -> str:
        """Retrieve related ADRs and context docs via RAG. Gracefully degrades."""
        try:
            from app.services.embeddings import get_embedding_service
            from app.services.vector_store import get_vector_store, COLLECTION_ADRS, COLLECTION_CONTEXT

            vs = get_vector_store()
            if not vs:
                return ""

            query_text = f"{request.title}\n{request.description}"
            embedding = get_embedding_service().embed(query_text)

            sections = []

            # Related existing ADRs
            adr_hits = vs.search(COLLECTION_ADRS, embedding, limit=3)
            if adr_hits:
                adr_texts = []
                for h in adr_hits:
                    adr_texts.append(f"- {h.get('document', '')[:500]}")
                sections.append("## Related Existing Decisions\n" + "\n".join(adr_texts))

            # Relevant context documents
            doc_hits = vs.search(COLLECTION_CONTEXT, embedding, limit=2)
            if doc_hits:
                doc_texts = []
                for h in doc_hits:
                    doc_texts.append(f"- {h.get('document', '')[:500]}")
                sections.append("## Relevant Context Documents\n" + "\n".join(doc_texts))

            if sections:
                return "\n\n".join(sections) + "\n\nConsider these when making your decision. Ensure consistency with existing ADRs.\n"
            return ""
        except Exception:
            return ""

    def generate(self, request: ADRGenerationRequest) -> GeneratedADR:
        """
        Generate an ADR using AI with RAG-augmented context.
        Retrieves related ADRs and context docs before generation.
        """

        if not self.api_key:
            raise AIGenerationError(
                "AI_API_KEY not configured. "
                "Set AI_API_KEY environment variable to enable AI generation."
            )

        # Retrieve RAG context (gracefully degrades to empty string)
        rag_context = self._retrieve_rag_context(request)

        prompt = self._build_prompt(request)
        if rag_context:
            prompt = rag_context + "\n\n" + prompt
        
        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {
                        "role": "system",
                        "content": "You are an expert software architect specializing in Architecture Decision Records. Generate detailed, well-structured ADRs in JSON format."
                    },
                    {
                        "role": "user",
                        "content": prompt
                    }
                ],
                temperature=0.7,
                max_tokens=2000,
                response_format={"type": "json_object"}
            )
            
            content = response.choices[0].message.content
            return self._parse_response(content)
            
        except Exception as e:
            raise AIGenerationError(f"AI generation failed: {str(e)}")
    
    async def generate_async(self, request: ADRGenerationRequest) -> GeneratedADR:
        """Async wrapper for generate"""
        import asyncio
        return await asyncio.to_thread(self.generate, request)


# =============================================================================
# Singleton Instance
# =============================================================================

_generator: Optional[ADRGenerator] = None


def get_generator() -> ADRGenerator:
    """Get or create the ADR generator instance"""
    global _generator
    if _generator is None:
        _generator = ADRGenerator()
    return _generator
