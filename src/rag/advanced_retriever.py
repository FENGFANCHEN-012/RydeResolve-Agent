"""
Advanced RAG Retriever
Combines query rewriting, hybrid search, re-ranking, and confidence scoring
for production-grade retrieval quality.

Pipeline:
1. Query Rewriting → expand user query into variants
2. Multi-query Retrieval → search with each variant
3. Hybrid Fusion → merge vector + BM25 results
4. Re-ranking → LLM-based precision scoring
5. Confidence Scoring → decide if results are good enough
"""
import asyncio
from src.rag.query_rewriter import query_rewriter
from src.rag.hybrid_search import hybrid_searcher
from src.rag.reranker import simple_reranker, llm_reranker
from src.rag.confidence_scorer import confidence_scorer, fallback_handler
from src.rag.retriever import DocumentRetriever


class AdvancedRetriever:
    """
    Production-grade retriever with multi-stage optimization.
    """

    def __init__(
        self,
        use_query_rewrite: bool = True,
        use_hybrid_search: bool = True,
        use_rerank: bool = True,
        use_confidence_scoring: bool = True,
        use_llm_rerank: bool = False,  # LLM rerank is slower but more accurate
    ):
        self.use_query_rewrite = use_query_rewrite
        self.use_hybrid_search = use_hybrid_search
        self.use_rerank = use_rerank
        self.use_confidence_scoring = use_confidence_scoring
        self.use_llm_rerank = use_llm_rerank

        self.base_retriever = DocumentRetriever()

    async def retrieve(
        self,
        query: str,
        top_k: int = 5,
        collection_name: str | None = None,
    ) -> dict:
        """
        Advanced retrieval with full pipeline.

        Returns:
            {
                "results": list[dict],  # ranked chunks
                "confidence": float,
                "should_answer": bool,
                "metrics": dict,
                "query_variants": list[str],
            }
        """
        # Stage 1: Query Rewriting
        query_variants = [query]
        if self.use_query_rewrite:
            query_variants = await query_rewriter.rewrite(query)

        # Stage 2: Multi-query Retrieval
        all_results = []
        for qv in query_variants:
            if self.use_hybrid_search:
                results = hybrid_searcher.search(qv, top_k=top_k * 2)
            else:
                results = self.base_retriever.retrieve(qv, top_k=top_k * 2, collection_name=collection_name)
            all_results.extend(results)

        # Deduplicate by clause text
        seen = set()
        deduped = []
        for r in all_results:
            key = r.get("clause", "")[:200]
            if key not in seen:
                seen.add(key)
                deduped.append(r)

        # Stage 3: Re-ranking
        if self.use_rerank and deduped:
            if self.use_llm_rerank:
                ranked = await llm_reranker.rerank(query, deduped, top_k=top_k * 2)
            else:
                ranked = simple_reranker.rerank(query, deduped, top_k=top_k * 2)
        else:
            ranked = deduped

        # Stage 4: Confidence Scoring
        if self.use_confidence_scoring:
            score = confidence_scorer.score_retrieval(query, ranked[:top_k])
        else:
            score = {
                "confidence": 1.0,
                "should_answer": True,
                "reason": "Scoring disabled",
                "metrics": {},
            }

        return {
            "results": ranked[:top_k],
            "confidence": score["confidence"],
            "should_answer": score["should_answer"],
            "metrics": score["metrics"],
            "query_variants": query_variants,
            "reason": score["reason"],
        }

    def invalidate_indexes(self):
        """Call after adding new documents."""
        hybrid_searcher.invalidate_index()


# Singleton
advanced_retriever = AdvancedRetriever()
