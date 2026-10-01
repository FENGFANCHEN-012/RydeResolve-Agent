"""
RAG Retriever
Retrieves relevant document chunks via vector similarity search, from ChromaDB
(HTTP or local persistent client) or, with VECTOR_BACKEND=qdrant, from Qdrant
Cloud using hybrid dense + BM25 search.
"""
from src import config
from src.rag.indexer import _get_chroma_client, ManualEmbeddingFunction
from src.rag.query_builder import TYPE_HINTS
from src.rag.policy_topics import TOPICS


_DISPUTE_CACHE: dict[tuple, list[dict]] = {}

# Section-tag ranking (D12). A chunk tagged with the dispute's type or "general" moves up,
# one tagged "none" moves down; the weight is on the scale of rank-based (RRF) scores.
# 0.001 was the best trade-off on the 27 eval cases: Hit@1 0.815 -> 0.963 with the right
# type, and with a deliberately wrong type the right section still stays in the top 3.
# Worst case (every runner-up matches a wrong type) the plain top hit drops to 4th, still
# inside the 5 clauses agents get. Larger weights act like a hard filter and hide rules.
TAG_WEIGHT = 0.001
CANDIDATE_POOL = 20
_RRF_K = 60


def rank_by_tags(chunks: list[dict], dispute_type: str, weight: float = TAG_WEIGHT) -> list[dict]:
    """Re-rank search results (best first) by their section tags. Untagged chunks keep
    their place relative to each other; nothing is ever removed."""
    def score(item):
        rank, chunk = item
        types = set((chunk.get("dispute_types") or "").split(",")) - {""}
        tag = 1 if (dispute_type in types or "general" in types) else (-1 if types == {"none"} else 0)
        return 1.0 / (_RRF_K + rank + 1) + weight * tag
    return [c for _, c in sorted(enumerate(chunks), key=score, reverse=True)]


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
        any_tags: tuple[str, ...] | None = None,
    ) -> list[dict]:
        """
        Retrieve top-k relevant document chunks for a given query.

        Returns list of dicts with: clause, source, section, similarity, chunk_index
        """
        if self.store is not None:
            return self.store.search(query, top_k=top_k, any_tags=any_tags)

        try:
            collection = self._get_collection(collection_name)
        except Exception as e:
            print(f"Warning: Could not connect to ChromaDB: {e}")
            return []

        where = None
        if any_tags:
            conds = [{f"dt_{t}": True} for t in any_tags]
            where = conds[0] if len(conds) == 1 else {"$or": conds}
        results = collection.query(
            query_texts=[query],
            n_results=min(top_k, 20),
            include=["documents", "metadatas", "distances"],
            **({"where": where} if where else {}),
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
                "dispute_types": meta.get("dispute_types", ""),
            })

        return parsed

    def retrieve_for_dispute(
        self,
        dispute_type: str,
        dispute_description: str,
        top_k: int = 5,
        collection_name: str | None = None,
    ) -> list[dict]:
        """Retrieve document chunks relevant to a specific dispute type: search a wider
        pool with the complaint plus the type's hint words, rank it by section tags, keep top_k."""
        # The complaint stays the query: a query built from the Collector's facts lost the
        # A/B (Hit@1 0.56 vs 0.82, D12); the type hint is official help-centre vocabulary
        type_context = TYPE_HINTS.get(dispute_type, "")
        query = f"{dispute_description} {type_context}".strip()
        # Passenger, Driver and Policy all ask the same question for one dispute: search once
        key = (collection_name, query, top_k)
        if key not in _DISPUTE_CACHE:
            if len(_DISPUTE_CACHE) > 256:
                _DISPUTE_CACHE.clear()
            pool = self.retrieve(query, top_k=max(top_k, CANDIDATE_POOL), collection_name=collection_name)
            _DISPUTE_CACHE[key] = rank_by_tags(pool, dispute_type)[:top_k]
        return [dict(c) for c in _DISPUTE_CACHE[key]]


def _topic_cache_key(topic: str, top_k: int, collection_name):
    return ("topic", topic, top_k, collection_name)


def retrieve_topic(retriever: "DocumentRetriever", topic: str, top_k: int = 2,
                   collection_name: str | None = None) -> list[dict]:
    """Clauses for one catalogue topic (src/rag/policy_topics.py): its official wording,
    searched only among sections tagged with the topic's types. Unknown topic -> []."""
    if topic not in TOPICS:
        return []
    key = _topic_cache_key(topic, top_k, collection_name)
    if key not in _DISPUTE_CACHE:
        words, tags = TOPICS[topic]
        hits = retriever.retrieve(words, top_k=top_k * 3, collection_name=collection_name, any_tags=tags)
        # Distinct sections: a long section split into chunks must not fill a topic twice
        seen, distinct = set(), []
        for c in hits:
            if (c.get("source"), c.get("section")) not in seen:
                seen.add((c.get("source"), c.get("section")))
                distinct.append(c)
        _DISPUTE_CACHE[key] = distinct[:top_k]
    return [dict(c) for c in _DISPUTE_CACHE[key]]


# Backward-compatible alias
PolicyRetriever = DocumentRetriever
