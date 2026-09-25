"""
Qdrant vector store (VECTOR_BACKEND=qdrant).

Each chunk is stored with two vectors:
- "dense":  semantic embedding (fastembed, BAAI/bge-small-en-v1.5 by default)
- "sparse": BM25 keyword weights (fastembed, Qdrant/bm25; IDF applied by Qdrant)

A search runs both and fuses the two rankings with Reciprocal Rank Fusion, so
exact policy terms ("no-show fee", "grace period") and paraphrases both match.
Embeddings are computed locally: no API key or quota is needed, and every
teammate gets identical vectors.
"""
import threading
import uuid

from qdrant_client import QdrantClient, models

from src import config

_models_lock = threading.Lock()
_dense_model = None
_sparse_model = None


def _get_models():
    """Load the fastembed models once per process (first call downloads them)."""
    global _dense_model, _sparse_model
    with _models_lock:
        if _dense_model is None:
            from fastembed import SparseTextEmbedding, TextEmbedding
            _dense_model = TextEmbedding(config.QDRANT_DENSE_MODEL)
            _sparse_model = SparseTextEmbedding(config.QDRANT_SPARSE_MODEL)
    return _dense_model, _sparse_model


class QdrantStore:
    """Index and hybrid-search policy chunks in one Qdrant collection."""

    def __init__(self, collection_name: str | None = None):
        if not config.QDRANT_URL:
            raise RuntimeError("VECTOR_BACKEND=qdrant but QDRANT_URL is not set in .env")
        # gRPC: about 3x faster than REST for each search from Singapore to the cloud cluster
        self.client = QdrantClient(
            url=config.QDRANT_URL, api_key=config.QDRANT_API_KEY or None, prefer_grpc=True, timeout=60,
        )
        self.collection = collection_name or config.QDRANT_COLLECTION

    def ensure_collection(self) -> None:
        """Create the collection if it does not exist yet."""
        if self.client.collection_exists(self.collection):
            return
        dense, _ = _get_models()
        dim = len(next(iter(dense.embed(["dimension probe"]))))
        self.client.create_collection(
            collection_name=self.collection,
            vectors_config={"dense": models.VectorParams(size=dim, distance=models.Distance.COSINE)},
            sparse_vectors_config={"sparse": models.SparseVectorParams(modifier=models.Modifier.IDF)},
        )

    def upsert(self, chunks: list[dict]) -> int:
        """
        Store chunks. Each chunk: {"id": str, "text": str, "metadata": dict}.
        Point ids are derived from the chunk id, so re-indexing overwrites
        instead of duplicating.
        """
        if not chunks:
            return 0
        self.ensure_collection()
        dense, sparse = _get_models()
        texts = [c["text"] for c in chunks]
        dense_vecs = list(dense.embed(texts))
        sparse_vecs = list(sparse.embed(texts))
        points = [
            models.PointStruct(
                id=str(uuid.uuid5(uuid.NAMESPACE_URL, c["id"])),
                vector={
                    "dense": d.tolist(),
                    "sparse": models.SparseVector(indices=s.indices.tolist(), values=s.values.tolist()),
                },
                payload={**c["metadata"], "chunk_id": c["id"], "text": c["text"]},
            )
            for c, d, s in zip(chunks, dense_vecs, sparse_vecs)
        ]
        # Small batches: one large request can hit the write timeout on a slow uplink
        self.client.upload_points(
            collection_name=self.collection, points=points, batch_size=16, max_retries=3, wait=True,
        )
        return len(points)

    def search(self, query: str, top_k: int = 5) -> list[dict]:
        """Hybrid search. Returns the same dict shape as the Chroma retriever."""
        dense, sparse = _get_models()
        q_dense = next(iter(dense.query_embed(query))).tolist()
        q_sparse = next(iter(sparse.query_embed(query)))
        limit = min(top_k, 20)
        result = self.client.query_points(
            collection_name=self.collection,
            prefetch=[
                models.Prefetch(query=q_dense, using="dense", limit=limit * 4),
                models.Prefetch(
                    query=models.SparseVector(indices=q_sparse.indices.tolist(), values=q_sparse.values.tolist()),
                    using="sparse",
                    limit=limit * 4,
                ),
            ],
            query=models.FusionQuery(fusion=models.Fusion.RRF),
            limit=limit,
            with_payload=True,
        )
        return [
            {
                "clause": p.payload.get("text", ""),
                "source": p.payload.get("title", "Unknown"),
                "section": p.payload.get("section", ""),
                "file_type": p.payload.get("file_type", ""),
                # RRF fusion score (rank-based), not a cosine similarity
                "similarity": round(p.score, 4),
                "chunk_index": p.payload.get("chunk_index", 0),
            }
            for p in result.points
        ]

    def count(self) -> int:
        if not self.client.collection_exists(self.collection):
            return 0
        return self.client.count(self.collection, exact=True).count

    def delete_collection(self) -> None:
        if self.client.collection_exists(self.collection):
            self.client.delete_collection(self.collection)
