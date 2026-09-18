"""
RAG Indexer
Indexes Ryde platform policy documents into Tencent VectorDB.
"""
from src.config import VECTORDB_API_URL, VECTORDB_COLLECTION


class PolicyIndexer:
    """Indexes policy documents for RAG retrieval."""

    # Policy document sources
    POLICY_SOURCES = [
        "Terms of Use",
        "Code of Conduct",
        "Cancellation Policy",
        "Refund Policy",
        "Driver Guidelines",
        "Safety Standards",
        "Ryde+ Subscription Terms",
        "Privacy Policy",
    ]

    async def index_policies(self, documents: list[dict]) -> int:
        """
        Index policy documents into Tencent VectorDB.
        
        Args:
            documents: list of {title, content, section, url}
        
        Returns:
            number of chunks indexed
        """
        # TODO: 
        # 1. Split documents into chunks
        # 2. Generate embeddings via Tencent Embedding API
        # 3. Store in Tencent VectorDB
        count = 0
        for doc in documents:
            chunks = self._chunk_document(doc["content"])
            for chunk in chunks:
                # TODO: embed and store
                count += 1
        return count

    def _chunk_document(self, text: str, chunk_size: int = 500) -> list[str]:
        """Split document into chunks for embedding."""
        words = text.split()
        chunks = []
        for i in range(0, len(words), chunk_size):
            chunks.append(" ".join(words[i : i + chunk_size]))
        return chunks
