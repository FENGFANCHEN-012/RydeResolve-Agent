"""
Google Gemini Embedding Client
Uses the Gemini API for embedding generation.

API: https://aistudio.google.com/app/apikey
Model: gemini-embedding-2 (3072 dimensions)
Free tier: generous daily limits

Default: deterministic local hash embedding, independent of the LLM API key.
Set EMBEDDING_PROVIDER=gemini for both indexing and retrieval to opt in to
Gemini embeddings, then re-index the policy collection.
"""
import hashlib
import numpy as np
import google.generativeai as genai

from src.config import (
    LLM_API_KEY,
    EMBEDDING_PROVIDER,
    EMBEDDING_MODEL,
    EMBEDDING_DIMENSION,
)


class GeminiEmbeddingClient:
    """
    Calls Google Gemini Embedding API.
    Free: generous daily limits.
    """

    def __init__(self):
        self.api_key = LLM_API_KEY
        self.model = f"models/{EMBEDDING_MODEL}"
        self._configured = False

    def _ensure_configured(self):
        if not self._configured:
            genai.configure(api_key=self.api_key)
            self._configured = True

    @property
    def is_available(self) -> bool:
        return bool(self.api_key)

    async def embed(self, text: str) -> list[float] | None:
        """Get embedding vector for a single text."""
        if not self.is_available:
            return None

        try:
            self._ensure_configured()
            result = genai.embed_content(
                model=self.model,
                content=text,
                task_type="retrieval_document",
            )
            return result["embedding"]
        except Exception as e:
            print(f"Gemini embedding failed: {e}")
            return None

    async def embed_batch(self, texts: list[str]) -> list[list[float] | None]:
        """Get embeddings for multiple texts (one API call per text)."""
        results = []
        for text in texts:
            vec = await self.embed(text)
            results.append(vec)
        return results


class SimpleHashEmbedding:
    """
    Local embedding provider for reproducible policy retrieval.
    Uses word-level hashing to create a fixed-size vector.
    """

    DIM = 3072  # Match Gemini embedding dimension

    def __call__(self, input: list[str]) -> list[list[float]]:
        return [self._embed(text) for text in input]

    def _embed(self, text: str) -> list[float]:
        vec = np.zeros(self.DIM, dtype=np.float32)
        words = text.lower().split()
        for word in words:
            h = int(hashlib.md5(word.encode()).hexdigest(), 16) % self.DIM
            vec[h] += 1.0
        norm = np.linalg.norm(vec)
        if norm > 0:
            vec = vec / norm
        return vec.tolist()


class EmbeddingManager:
    """
    Uses the same provider for indexing and retrieval, regardless of whether
    an LLM API key is configured for text generation.
    """

    def __init__(self):
        self.gemini_client = GeminiEmbeddingClient()
        self.hash_embedding = SimpleHashEmbedding()
        self._mode = (
            "gemini" if EMBEDDING_PROVIDER == "gemini" and self.gemini_client.is_available
            else "hash"
        )

    @property
    def mode(self) -> str:
        return self._mode

    @property
    def dimension(self) -> int:
        if self._mode == "gemini":
            return EMBEDDING_DIMENSION
        return SimpleHashEmbedding.DIM

    async def embed(self, text: str) -> list[float]:
        """Get an embedding from the selected provider."""
        if self._mode == "gemini":
            vec = await self.gemini_client.embed(text)
            if vec is None:
                raise RuntimeError("Gemini embedding failed; refusing to mix embedding providers")
            return vec
        return self.hash_embedding._embed(text)

    async def embed_batch(self, texts: list[str]) -> list[list[float]]:
        """Get embeddings for multiple texts."""
        if self._mode == "gemini":
            results = await self.gemini_client.embed_batch(texts)
            if any(vec is None for vec in results):
                raise RuntimeError("Gemini embedding failed; refusing to mix embedding providers")
            return results
        return self.hash_embedding(texts)


# Singleton
embedding_manager = EmbeddingManager()
