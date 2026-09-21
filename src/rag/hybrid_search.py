"""
Hybrid Search: Vector + BM25 Keyword Search
Combines semantic similarity (vector) with lexical matching (BM25)
for better recall and precision.
"""
import re
import math
from collections import Counter

from src.rag.retriever import DocumentRetriever


class BM25Searcher:
    """Simple in-memory BM25 keyword search over indexed documents."""

    def __init__(self, k1: float = 1.5, b: float = 0.75):
        self.k1 = k1
        self.b = b
        self.documents = []
        self.doc_freqs = []
        self.doc_lengths = []
        self.avg_doc_length = 0
        self.term_df = Counter()
        self.N = 0

    def index(self, documents: list[str]):
        """Index documents for BM25 search."""
        self.documents = documents
        self.doc_freqs = []
        self.doc_lengths = []
        self.term_df = Counter()

        for doc in documents:
            tokens = self._tokenize(doc)
            freq = Counter(tokens)
            self.doc_freqs.append(freq)
            self.doc_lengths.append(len(tokens))

            for term in set(tokens):
                self.term_df[term] += 1

        self.N = len(documents)
        self.avg_doc_length = sum(self.doc_lengths) / max(self.N, 1)

    def _tokenize(self, text: str) -> list[str]:
        """Simple tokenization: lowercase, alphanumeric only."""
        return re.findall(r'[a-z0-9]+', text.lower())

    def search(self, query: str, top_k: int = 10) -> list[tuple[int, float]]:
        """
        Search documents and return (doc_index, score) tuples sorted by score.
        """
        query_tokens = self._tokenize(query)
        if not query_tokens:
            return []

        scores = []
        for i in range(self.N):
            score = self._score_doc(i, query_tokens)
            if score > 0:
                scores.append((i, score))

        scores.sort(key=lambda x: x[1], reverse=True)
        return scores[:top_k]

    def _score_doc(self, doc_idx: int, query_tokens: list[str]) -> float:
        """Calculate BM25 score for a document."""
        score = 0.0
        doc_len = self.doc_lengths[doc_idx]
        doc_freq = self.doc_freqs[doc_idx]

        for term in query_tokens:
            if term not in doc_freq:
                continue

            # IDF
            df = self.term_df.get(term, 0)
            idf = math.log((self.N - df + 0.5) / (df + 0.5) + 1)

            # Term frequency component
            tf = doc_freq[term]
            denom = tf + self.k1 * (1 - self.b + self.b * doc_len / self.avg_doc_length)
            score += idf * (tf * (self.k1 + 1)) / denom

        return score


class HybridSearcher:
    """
    Combines vector search (ChromaDB) with BM25 keyword search.
    Uses Reciprocal Rank Fusion (RRF) to merge results.
    """

    RRF_K = 60  # RRF constant

    def __init__(self):
        self.retriever = DocumentRetriever()
        self.bm25 = BM25Searcher()
        self._bm25_indexed = False

    def _ensure_bm25_indexed(self):
        """Build BM25 index from current ChromaDB collection."""
        if self._bm25_indexed:
            return

        try:
            collection = self.retriever._get_collection()
            # Get all documents
            all_data = collection.get(include=["documents", "metadatas"])
            docs = all_data.get("documents", [])
            if docs:
                self.bm25.index(docs)
                self._bm25_indexed = True
        except Exception as e:
            print(f"BM25 indexing failed: {e}")

    def search(
        self,
        query: str,
        top_k: int = 10,
        vector_weight: float = 0.7,
        keyword_weight: float = 0.3,
    ) -> list[dict]:
        """
        Hybrid search combining vector and keyword search with RRF.

        Args:
            query: Search query
            top_k: Number of results to return
            vector_weight: Weight for vector search scores (0-1)
            keyword_weight: Weight for BM25 scores (0-1)

        Returns:
            List of result dicts with merged scores
        """
        # 1. Vector search
        vector_results = self.retriever.retrieve(query, top_k=top_k * 2)

        # 2. Keyword search (BM25)
        self._ensure_bm25_indexed()
        keyword_results = []
        if self._bm25_indexed:
            bm25_scores = self.bm25.search(query, top_k=top_k * 2)
            # Map BM25 results to same format
            try:
                collection = self.retriever._get_collection()
                all_data = collection.get(include=["documents", "metadatas"])
                docs = all_data.get("documents", [])
                metas = all_data.get("metadatas", [])
                for idx, score in bm25_scores:
                    if idx < len(docs):
                        keyword_results.append({
                            "clause": docs[idx],
                            "source": metas[idx].get("title", "Unknown") if idx < len(metas) else "Unknown",
                            "section": metas[idx].get("section", "") if idx < len(metas) else "",
                            "file_type": metas[idx].get("file_type", "") if idx < len(metas) else "",
                            "similarity": min(score / 10.0, 1.0),  # Normalize BM25 score
                            "chunk_index": metas[idx].get("chunk_index", 0) if idx < len(metas) else 0,
                            "_bm25_score": score,
                        })
            except Exception as e:
                print(f"BM25 result mapping failed: {e}")

        # 3. Reciprocal Rank Fusion
        fused = self._rrf_fuse(vector_results, keyword_results, top_k)
        return fused

    def _rrf_fuse(
        self,
        vector_results: list[dict],
        keyword_results: list[dict],
        top_k: int,
    ) -> list[dict]:
        """
        Merge vector and keyword results using Reciprocal Rank Fusion.
        """
        scores = {}

        # Vector results ranking
        for rank, result in enumerate(vector_results):
            key = (result["clause"], result["source"])
            if key not in scores:
                scores[key] = {"score": 0.0, "result": result}
            scores[key]["score"] += 1.0 / (self.RRF_K + rank + 1)

        # Keyword results ranking
        for rank, result in enumerate(keyword_results):
            key = (result["clause"], result["source"])
            if key not in scores:
                scores[key] = {"score": 0.0, "result": result}
            scores[key]["score"] += 1.0 / (self.RRF_K + rank + 1)

        # Sort by fused score
        sorted_results = sorted(scores.values(), key=lambda x: x["score"], reverse=True)

        # Format output
        output = []
        for item in sorted_results[:top_k]:
            result = dict(item["result"])
            result["fused_score"] = round(item["score"], 4)
            output.append(result)

        return output

    def invalidate_index(self):
        """Call this after adding new documents to rebuild BM25 index."""
        self._bm25_indexed = False


# Singleton
hybrid_searcher = HybridSearcher()
