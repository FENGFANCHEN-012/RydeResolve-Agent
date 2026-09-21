"""
RAG Retriever
Retrieves relevant policy clauses from ChromaDB via vector similarity search.

Supports both HTTP client (Docker) and persistent local client (dev mode).
"""
import chromadb

from src.config import CHROMA_HOST, CHROMA_PORT, CHROMA_COLLECTION, BASE_DIR
from src.rag.indexer import _get_chroma_client, _get_embedding_function


class PolicyRetriever:
    """Retrieves policy clauses via vector similarity search."""

    def __init__(self):
        self.client, self.mode = _get_chroma_client()
        self.embedding_fn = _get_embedding_function()

    def _get_collection(self):
        """Get the ChromaDB collection."""
        return self.client.get_collection(
            name=CHROMA_COLLECTION,
            embedding_function=self.embedding_fn,
        )

    def retrieve(
        self,
        query: str,
        top_k: int = 5,
    ) -> list[dict]:
        """
        Retrieve top-k relevant policy clauses for a given query.

        Args:
            query: Natural language query about the dispute
                   (e.g., "driver took a longer route and overcharged")
            top_k: Number of results to return

        Returns:
            List of dicts, each containing:
            - clause: The policy text chunk
            - source: The source document title
            - section: The section within the document
            - similarity: Similarity score (0-1, higher is better)
            - chunk_index: Position within the source document
        """
        try:
            collection = self._get_collection()
        except Exception as e:
            print(f"Warning: Could not connect to ChromaDB: {e}")
            return []

        results = collection.query(
            query_texts=[query],
            n_results=min(top_k, 10),
            include=["documents", "metadatas", "distances"],
        )

        # Parse results
        documents = results.get("documents", [[]])[0]
        metadatas = results.get("metadatas", [[]])[0]
        distances = results.get("distances", [[]])[0]

        parsed = []
        for doc, meta, dist in zip(documents, metadatas, distances):
            # ChromaDB returns L2 distance; convert to similarity (0-1)
            # Lower distance = higher similarity
            similarity = max(0.0, 1.0 - dist)
            parsed.append({
                "clause": doc,
                "source": meta.get("title", "Unknown"),
                "section": meta.get("section", ""),
                "similarity": round(similarity, 4),
                "chunk_index": meta.get("chunk_index", 0),
            })

        return parsed

    def retrieve_for_dispute(
        self,
        dispute_type: str,
        dispute_description: str,
        top_k: int = 5,
    ) -> list[dict]:
        """
        Retrieve policy clauses relevant to a specific dispute.

        Combines the dispute type and description into a richer query
        for better retrieval results.

        Args:
            dispute_type: e.g., "route_deviation", "no_show_charge"
            dispute_description: The rider's complaint text

        Returns:
            List of relevant policy clauses
        """
        # Enrich the query with dispute type context
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

        return self.retrieve(query, top_k=top_k)
