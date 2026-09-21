"""
Tencent Cloud Hunyuan Embedding Client
Uses the OpenAI-compatible Hunyuan API endpoint for embedding generation.

API: https://api.hunyuan.cloud.tencent.com/v1/embeddings
Model: hunyuan-embedding (1024 dimensions)
Free tier: 1,000,000 tokens (1 year expiry) after first activation

Fallback chain:
1. Hunyuan Embedding API (if LLM_API_KEY is set to Hunyuan key)
2. Simple hash-based embedding (for local dev without API key)
"""
import hashlib
import numpy as np
from openai import AsyncOpenAI

from src.config import (
    LLM_API_KEY,
    LLM_BASE_URL,
    HUNYUAN_EMBEDDING_MODEL,
)


class HunyuanEmbeddingClient:
    """
    Calls Tencent Hunyuan Embedding API via OpenAI-compatible endpoint.
    Free: 1M tokens after first activation.
    """

    def __init__(self):
        self.api_key = LLM_API_KEY
        self.base_url = LLM_BASE_URL
        self.model = HUNYUAN_EMBEDDING_MODEL
        self._client = None

    @property
    def is_available(self) -> bool:
        return bool(self.api_key)

    def _get_client(self):
        if self._client is None:
            self._client = AsyncOpenAI(
                api_key=self.api_key,
                base_url=self.base_url,
            )
        return self._client

    async def embed(self, text: str) -> list[float] | None:
        """Get embedding vector for a single text."""
        if not self.is_available:
            return None

        try:
            client = self._get_client()
            response = await client.embeddings.create(
                model=self.model,
                input=text,
            )
            return response.data[0].embedding
        except Exception as e:
            print(f"Hunyuan embedding failed: {e}")
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
    Fallback embedding for local dev without API keys.
    Uses word-level hashing to create a fixed-size vector.
    """

    DIM = 1024  # Match Hunyuan embedding dimension

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
    Manages embedding generation with fallback chain:
    1. Tencent Hunyuan Embedding (if LLM_API_KEY is set)
    2. Simple hash-based (always available)
    """

    def __init__(self):
        self.hunyuan_client = HunyuanEmbeddingClient()
        self.hash_embedding = SimpleHashEmbedding()
        self._mode = "hunyuan" if self.hunyuan_client.is_available else "hash"

    @property
    def mode(self) -> str:
        return self._mode

    @property
    def dimension(self) -> int:
        if self._mode == "hunyuan":
            return 1024  # Hunyuan embedding dimension
        return SimpleHashEmbedding.DIM

    async def embed(self, text: str) -> list[float]:
        """Get embedding vector for text with fallback."""
        if self._mode == "hunyuan":
            vec = await self.hunyuan_client.embed(text)
            if vec is not None:
                return vec
            print("Hunyuan embedding failed, falling back to hash embedding")
            return self.hash_embedding._embed(text)
        return self.hash_embedding._embed(text)

    async def embed_batch(self, texts: list[str]) -> list[list[float]]:
        """Get embeddings for multiple texts."""
        if self._mode == "hunyuan":
            results = await self.hunyuan_client.embed_batch(texts)
            final = []
            for i, vec in enumerate(results):
                if vec is not None:
                    final.append(vec)
                else:
                    final.append(self.hash_embedding._embed(texts[i]))
            return final
        return self.hash_embedding(texts)


# Singleton
embedding_manager = EmbeddingManager()
