"""
RAG Indexer
Indexes Ryde platform policy documents into ChromaDB for vector retrieval.

Supports two modes:
1. HttpClient — connects to a running ChromaDB server (Docker or standalone)
2. PersistentClient — uses local file-based storage (for development without Docker)

Embedding strategy:
- If LLM_API_KEY is set: uses OpenAI-compatible embedding API
- If no API key: uses a simple hash-based embedding (for local dev/testing only)
  This produces lower-quality retrieval but requires no downloads.
"""
import os
import hashlib
import numpy as np
import chromadb
from chromadb.api.types import EmbeddingFunction, Documents, Embeddings

from src.config import (
    CHROMA_HOST, CHROMA_PORT, CHROMA_COLLECTION,
    POLICIES_DIR, BASE_DIR,
    LLM_API_KEY, LLM_BASE_URL,
)

# Embedding dimension for fallback hash-based embeddings
FALLBACK_EMBED_DIM = 384


class SimpleHashEmbedding(EmbeddingFunction):
    """
    Fallback embedding function for local development without an API key.
    Uses word-level hashing to create a fixed-size vector. This is NOT production-
    quality but works for testing the RAG pipeline without downloading models.
    """

    def __init__(self, dim: int = FALLBACK_EMBED_DIM):
        self.dim = dim

    def __call__(self, input: Documents) -> Embeddings:
        return [self._embed(text) for text in input]

    def _embed(self, text: str) -> list[float]:
        """Create a simple bag-of-words hash embedding."""
        vec = np.zeros(self.dim, dtype=np.float32)
        words = text.lower().split()
        for word in words:
            h = int(hashlib.md5(word.encode()).hexdigest(), 16) % self.dim
            vec[h] += 1.0
        # Normalize
        norm = np.linalg.norm(vec)
        if norm > 0:
            vec = vec / norm
        return vec.tolist()

    def name(self):
        return "simple_hash_embedding"


def _get_embedding_function():
    """Get embedding function. Uses OpenAI-compatible API if key is set, else hash-based."""
    if LLM_API_KEY:
        try:
            from chromadb.utils.embedding_functions import OpenAIEmbeddingFunction
            return OpenAIEmbeddingFunction(
                api_key=LLM_API_KEY,
                base_url=LLM_BASE_URL,
                model_name="text-embedding-3-small",
            )
        except Exception as e:
            print(f"Warning: Could not init OpenAI embedding function: {e}")
    # Fallback: simple hash-based embedding for local dev
    return SimpleHashEmbedding()


def _get_chroma_client():
    """
    Get a ChromaDB client.
    Tries HttpClient first (for Docker/remote), falls back to PersistentClient (local dev).
    """
    # Try HTTP client first
    try:
        client = chromadb.HttpClient(host=CHROMA_HOST, port=CHROMA_PORT)
        # Test connection
        client.heartbeat()
        return client, "http"
    except Exception:
        pass

    # Fall back to persistent local client
    local_path = os.path.join(BASE_DIR, "chroma_data")
    os.makedirs(local_path, exist_ok=True)
    client = chromadb.PersistentClient(path=local_path)
    return client, "local"


class PolicyIndexer:
    """Indexes policy documents for RAG retrieval."""

    # Chunking settings
    CHUNK_SIZE = 500  # words per chunk
    CHUNK_OVERLAP = 50  # words of overlap between chunks

    def __init__(self):
        self.client, self.mode = _get_chroma_client()
        self.embedding_fn = _get_embedding_function()

    def get_or_create_collection(self):
        """Get or create the ChromaDB collection for policies."""
        return self.client.get_or_create_collection(
            name=CHROMA_COLLECTION,
            metadata={"description": "Ryde platform policy documents for RAG"},
            embedding_function=self.embedding_fn,
        )

    def index_policies(self, documents: list[dict] | None = None) -> int:
        """
        Index policy documents into ChromaDB.

        Args:
            documents: list of {id, title, content, source, section}
                      If None, loads from POLICIES_DIR.

        Returns:
            Number of chunks indexed.
        """
        if documents is None:
            documents = self._load_policy_files()

        collection = self.get_or_create_collection()

        count = 0
        for doc in documents:
            chunks = self._chunk_document(doc["content"])
            for i, chunk_text in enumerate(chunks):
                chunk_id = f"{doc['id']}_{i:04d}"
                metadata = {
                    "title": doc["title"],
                    "source": doc.get("source", doc["title"]),
                    "section": doc.get("section", ""),
                    "chunk_index": i,
                    "total_chunks": len(chunks),
                }

                # Upsert (idempotent — safe to re-run)
                collection.upsert(
                    ids=[chunk_id],
                    documents=[chunk_text],
                    metadatas=[metadata],
                )
                count += 1

        return count

    def _load_policy_files(self) -> list[dict]:
        """Load all .md files from the policies directory."""
        documents = []
        if not os.path.exists(POLICIES_DIR):
            print(f"Policies directory not found: {POLICIES_DIR}")
            return documents

        for filename in sorted(os.listdir(POLICIES_DIR)):
            if not filename.endswith(".md"):
                continue

            filepath = os.path.join(POLICIES_DIR, filename)
            with open(filepath, "r", encoding="utf-8") as f:
                content = f.read()

            doc_id = filename.replace(".md", "")
            title = doc_id.replace("_", " ").title()

            documents.append({
                "id": doc_id,
                "title": title,
                "content": content,
                "source": filename,
                "section": "",
            })

        return documents

    def _chunk_document(self, text: str, chunk_size: int | None = None, overlap: int | None = None) -> list[str]:
        """
        Split document into overlapping word chunks.
        """
        cs = chunk_size or self.CHUNK_SIZE
        ol = overlap or self.CHUNK_OVERLAP

        words = text.split()
        if len(words) <= cs:
            return [text]

        chunks = []
        start = 0
        while start < len(words):
            end = start + cs
            chunk = " ".join(words[start:end])
            chunks.append(chunk)
            start = end - ol  # overlap for context continuity

        return chunks

    def get_collection_stats(self) -> dict:
        """Get statistics about the indexed collection."""
        try:
            collection = self.client.get_collection(CHROMA_COLLECTION)
            count = collection.count()
            return {
                "collection": CHROMA_COLLECTION,
                "chunk_count": count,
                "mode": self.mode,
            }
        except Exception:
            return {
                "collection": CHROMA_COLLECTION,
                "chunk_count": 0,
                "mode": self.mode,
                "error": "Collection not found",
            }

    def clear_collection(self):
        """Delete the entire collection (for re-indexing)."""
        try:
            self.client.delete_collection(CHROMA_COLLECTION)
            print(f"Deleted collection: {CHROMA_COLLECTION}")
        except Exception:
            print(f"Collection {CHROMA_COLLECTION} does not exist, skipping delete.")
