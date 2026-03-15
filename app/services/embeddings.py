"""Embedding service — uses same OpenAI-compatible client as AI generator."""
import os
from openai import OpenAI

EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL", "text-embedding-3-small")


class EmbeddingError(Exception):
    pass


class EmbeddingService:
    def __init__(self):
        self.api_key = os.getenv("AI_API_KEY", "")
        self.base_url = os.getenv("AI_BASE_URL", "")
        self.model = EMBEDDING_MODEL
        kwargs = {"api_key": self.api_key}
        if self.base_url:
            kwargs["base_url"] = self.base_url
        self.client = OpenAI(**kwargs)

    def embed(self, text: str) -> list[float]:
        if not self.api_key:
            raise EmbeddingError("AI_API_KEY not configured")
        text = (text or "").strip()[:8000]
        if not text:
            raise EmbeddingError("Empty text")
        try:
            resp = self.client.embeddings.create(model=self.model, input=text)
            return resp.data[0].embedding
        except Exception as e:
            raise EmbeddingError(f"Embedding failed: {e}")

    def embed_batch(self, texts: list[str]) -> list[list[float]]:
        if not self.api_key:
            raise EmbeddingError("AI_API_KEY not configured")
        cleaned = [(t or "").strip()[:8000] for t in texts]
        cleaned = [t for t in cleaned if t]
        if not cleaned:
            return []
        try:
            resp = self.client.embeddings.create(model=self.model, input=cleaned)
            return [d.embedding for d in resp.data]
        except Exception as e:
            raise EmbeddingError(f"Batch embedding failed: {e}")


_service = None


def get_embedding_service():
    global _service
    if _service is None:
        _service = EmbeddingService()
    return _service
