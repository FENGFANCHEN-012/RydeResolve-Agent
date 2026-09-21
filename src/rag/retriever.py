"""
RAG Retriever
Retrieves relevant document chunks from ChromaDB via vector similarity search.
Supports both HTTP client (Docker) and persistent local client (dev mode).
"""
from src.rag.indexer import _get_chroma_client, ManualEmbeddingFunction


class DocumentRetriever:
    """Retrieves document chunks via vector similarity search."""

    def __init__(self):
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
            "no_show_charge": "driver did not show up cancellation fee no-show rider absent",
            "fare_dispute": "fare overcharging surge pricing promo code payment",
            "cancellation_refund": "cancellation refund fee rider driver cancel",
            "service_quality": "rude behavior unsafe driving detour rating retaliation",
            "property_damage": "rider damage vehicle mess cleaning fee spill",
            "safety_incident": "safety incident inappropriate behavior harassment",
        }
        type_context = type_mapping.get(dispute_type, "")
        query = f"{dispute_description} {type_context}".strip()
        return self.retrieve(query, top_k=top_k, collection_name=collection_name)


# Backward-compatible alias
PolicyRetriever = DocumentRetriever
