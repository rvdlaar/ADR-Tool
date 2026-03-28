"""
Supervision pass — checks generated ADR output against organizational memory (learnings).
Second-pass validation using the same LLM but focused on learned corrections.
"""
import json
import logging

logger = logging.getLogger(__name__)


async def supervise(generated_adr: dict, learnings: list[dict], generator) -> dict:
    """
    Second-pass supervision: check generated output against org memory.
    Returns {"passed": bool, "suggestions": [str]}.
    Only runs when learnings exist.
    """
    if not learnings:
        return {"passed": True, "suggestions": []}

    memory_rules = "\n".join(f"- {l['lesson']}" for l in learnings)

    try:
        import asyncio
        result = await asyncio.to_thread(
            _supervise_sync, generated_adr, memory_rules, generator
        )
        return result
    except Exception as e:
        logger.warning(f"Supervision pass failed: {e}")
        # Don't block generation if supervision fails
        return {"passed": True, "suggestions": []}


def _supervise_sync(generated_adr: dict, memory_rules: str, generator) -> dict:
    """Synchronous supervision call."""
    try:
        response = generator.client.chat.completions.create(
            model=generator.model,
            temperature=0.3,
            max_tokens=500,
            messages=[
                {
                    "role": "system",
                    "content": (
                        "You are a quality supervisor for architecture decision records.\n"
                        "Check if this ADR follows these organizational rules learned from "
                        "past corrections:\n\n"
                        f"{memory_rules}\n\n"
                        'Return JSON: {"passed": bool, "suggestions": ["specific fix 1", "specific fix 2"]}\n'
                        "Only flag clear violations. If the ADR is acceptable, return passed: true."
                    ),
                },
                {
                    "role": "user",
                    "content": json.dumps(generated_adr, indent=2)[:3000],
                },
            ],
            response_format={"type": "json_object"},
        )
        content = response.choices[0].message.content
        parsed = json.loads(content)
        return {
            "passed": bool(parsed.get("passed", True)),
            "suggestions": list(parsed.get("suggestions", [])),
        }
    except Exception as e:
        logger.warning(f"Supervision LLM call failed: {e}")
        return {"passed": True, "suggestions": []}
