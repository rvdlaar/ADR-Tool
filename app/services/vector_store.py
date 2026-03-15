"""ChromaDB vector store wrapper with self-healing reconnection."""
import os
import logging

logger = logging.getLogger(__name__)

CHROMA_URL = os.getenv("CHROMA_URL", "http://chromadb:8000")
COLLECTION_ADRS = "adrs"
COLLECTION_CONTEXT = "context_docs"


class VectorStore:
    def __init__(self):
        import chromadb
        host = CHROMA_URL.replace("http://", "").replace("https://", "").split(":")[0]
        port = int(CHROMA_URL.split(":")[-1])
        self.client = chromadb.HttpClient(host=host, port=port)
        self._collections = {}

    def _get_collection(self, name):
        if name not in self._collections:
            self._collections[name] = self.client.get_or_create_collection(
                name=name, metadata={"hnsw:space": "cosine"}
            )
        return self._collections[name]

    def upsert(self, collection_name, doc_id, embedding, text, metadata=None):
        coll = self._get_collection(collection_name)
        coll.upsert(
            ids=[doc_id],
            embeddings=[embedding],
            documents=[text[:5000]],
            metadatas=[metadata or {}]
        )

    def search(self, collection_name, query_embedding, limit=5):
        coll = self._get_collection(collection_name)
        results = coll.query(
            query_embeddings=[query_embedding],
            n_results=min(limit, 20),
            include=["documents", "metadatas", "distances"]
        )
        hits = []
        if results and results["ids"] and results["ids"][0]:
            for i, doc_id in enumerate(results["ids"][0]):
                hits.append({
                    "id": doc_id,
                    "document": results["documents"][0][i] if results["documents"] else "",
                    "metadata": results["metadatas"][0][i] if results["metadatas"] else {},
                    "distance": results["distances"][0][i] if results["distances"] else 0,
                    "score": round(1 - (results["distances"][0][i] if results["distances"] else 0), 4),
                })
        return hits

    def delete(self, collection_name, doc_id):
        try:
            coll = self._get_collection(collection_name)
            coll.delete(ids=[doc_id])
        except Exception as e:
            logger.warning(f"ChromaDB delete failed for {doc_id}: {e}")

    def count(self, collection_name):
        try:
            coll = self._get_collection(collection_name)
            return coll.count()
        except Exception as e:
            logger.warning(f"ChromaDB count failed for {collection_name}: {e}")
            return -1  # -1 signals error, 0 means genuinely empty

    def is_healthy(self) -> bool:
        try:
            self.client.heartbeat()
            return True
        except Exception:
            return False


_store = None
_last_failure = 0


def get_vector_store():
    """Get vector store with self-healing: retries connection if previously failed."""
    global _store, _last_failure
    import time

    if _store is not None:
        return _store

    # Don't retry more than once every 30 seconds
    now = time.time()
    if _last_failure and (now - _last_failure) < 30:
        return None

    try:
        _store = VectorStore()
        _last_failure = 0
        return _store
    except Exception as e:
        logger.warning(f"ChromaDB unavailable: {e}")
        _last_failure = now
        return None


def reset_vector_store():
    """Force reconnection on next request."""
    global _store, _last_failure
    _store = None
    _last_failure = 0
