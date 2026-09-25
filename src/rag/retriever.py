"""
RAG Retriever
Retrieves relevant document chunks via vector similarity search, from ChromaDB
(HTTP or local persistent client) or, with VECTOR_BACKEND=qdrant, from Qdrant
Cloud using hybrid dense + BM25 search.
"""
from src import config
from src.rag.indexer import _get_chroma_client, ManualEmbeddingFunction


class DocumentRetriever:
    """Retrieves document chunks via vector similarity search."""

    def __init__(self):
        self.store = None
        if config.VECTOR_BACKEND == "qdrant":
            from src.rag.qdrant_store import QdrantStore
            self.store = QdrantStore()
            self.client, self.mode = None, "qdrant"
        else:
            self.client, self.mode = _get_chroma_client()
        self.embedding_fn = ManualEmbeddingFunction()

    def _get_collection(self, collection_name: str | None = None):
        from src.config import CHROMA_COLLECTION
        return self.client.get_collection(
            name=collection_name or CHROMA_COLLECTION,
            embedding_function=self.embedding_fn,
        )

    def retrieve(
        self,
        query: str,
        top_k: int = 5,
        collection_name: str | None = None,
    ) -> list[dict]:
        """
        Retrieve top-k relevant document chunks for a given query.

        Returns list of dicts with: clause, source, section, similarity, chunk_index
        """
        if self.store is not None:
            return self.store.search(query, top_k=top_k)

        try:
            collection = self._get_collection(collection_name)
        except Exception as e:
            print(f"Warning: Could not connect to ChromaDB: {e}")
            return []

        results = collection.query(
            query_texts=[query],
            n_results=min(top_k, 20),
            include=["documents", "metadatas", "distances"],
        )

        documents = results.get("documents", [[]])[0]
        metadatas = results.get("metadatas", [[]])[0]
        distances = results.get("distances", [[]])[0]

        parsed = []
        for doc, meta, dist in zip(documents, metadatas, distances):
            similarity = max(0.0, 1.0 - dist)
            parsed.append({
                "clause": doc,
                "source": meta.get("title", "Unknown"),
                "section": meta.get("section", ""),
                "file_type": meta.get("file_type", ""),
                "similarity": round(similarity, 4),
                "chunk_index": meta.get("chunk_index", 0),
            })

        return parsed

    def retrieve_for_dispute(
        self,
        dispute_type: str,
        dispute_description: str,
        top_k: int = 5,
        collection_name: str | None = None,
    ) -> list[dict]:
        """Retrieve document chunks relevant to a specific dispute type."""
        type_mapping = {
            "route_deviation": "driver took longer route overcharged fare route compliance",
            "no_show": "no-show charge rider present driver arrival grace period cancellation fee",
            "no_show_charge": "no-show charge rider present driver arrival grace period cancellation fee",
            "fare_dispute": "fare overcharging surge pricing promo code payment",
            "cancellation_refund": "cancellation refund fee rider driver cancel",
            "service_quality": "rude behavior unsafe driving detour rating retaliation",
            "property_damage": "rider damage vehicle mess cleaning fee spill",
            "safety_incident": "safety incident inappropriate behavior harassment",
            "driver_rights": "driver appeal cleaning claim compensation receipt photo evidence",
            "accident_liability": "safety incident P0 escalation injury accident human review",
        }
        type_context = type_mapping.get(dispute_type, "")
        query = f"{dispute_description} {type_context}".strip()
        return self.retrieve(query, top_k=top_k, collection_name=collection_name)


# Backward-compatible alias
PolicyRetriever = DocumentRetriever
