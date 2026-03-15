"""ChromaDB vector store wrapper."""
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
        except Exception:
            pass

    def count(self, collection_name):
        try:
            coll = self._get_collection(collection_name)
            return coll.count()
        except Exception:
            return 0


_store = None


def get_vector_store():
    global _store
    if _store is None:
        try:
            _store = VectorStore()
        except Exception as e:
            logger.warning(f"ChromaDB unavailable: {e}")
            return None
    return _store
