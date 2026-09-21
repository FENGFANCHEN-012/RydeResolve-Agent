"""
Confidence Scoring for RAG Retrieval Quality
Evaluates retrieval quality and decides whether to answer or fallback.
"""
import math


class ConfidenceScorer:
    """
    Scores the quality of retrieved results and determines
    whether the RAG system should attempt to answer.
    """

    # Thresholds
    MIN_SIMILARITY = 0.25      # Minimum avg similarity to trust results
    MIN_TOP_SIMILARITY = 0.35  # Minimum top result similarity
    MIN_COVERAGE = 0.6         # Minimum query term coverage

    def score_retrieval(
        self,
        query: str,
        results: list[dict],
    ) -> dict:
        """
        Score retrieval quality and return confidence metrics.

        Returns:
            {
                "confidence": float (0-1),
                "should_answer": bool,
                "reason": str,
                "metrics": {
                    "avg_similarity": float,
                    "top_similarity": float,
                    "coverage": float,
                    "result_count": int,
                }
            }
        """
        if not results:
            return {
                "confidence": 0.0,
                "should_answer": False,
                "reason": "No relevant documents found",
                "metrics": {
                    "avg_similarity": 0.0,
                    "top_similarity": 0.0,
                    "coverage": 0.0,
                    "result_count": 0,
                }
            }

        # 1. Similarity scores
        similarities = [r.get("similarity", 0) for r in results]
        avg_sim = sum(similarities) / len(similarities)
        top_sim = max(similarities) if similarities else 0

        # 2. Query term coverage
        coverage = self._calculate_coverage(query, results)

        # 3. Calculate overall confidence
        # Weight: top_sim 40%, avg_sim 30%, coverage 30%
        confidence = (
            min(top_sim / 0.5, 1.0) * 0.4 +
            min(avg_sim / 0.4, 1.0) * 0.3 +
            coverage * 0.3
        )
        confidence = round(min(confidence, 1.0), 4)

        # 4. Decide whether to answer
        should_answer = (
            top_sim >= self.MIN_TOP_SIMILARITY and
            avg_sim >= self.MIN_SIMILARITY and
            coverage >= self.MIN_COVERAGE
        )

        if not should_answer:
            if top_sim < self.MIN_TOP_SIMILARITY:
                reason = f"Top result similarity ({top_sim:.2f}) below threshold ({self.MIN_TOP_SIMILARITY})"
            elif avg_sim < self.MIN_SIMILARITY:
                reason = f"Average similarity ({avg_sim:.2f}) below threshold ({self.MIN_SIMILARITY})"
            else:
                reason = f"Query coverage ({coverage:.2f}) below threshold ({self.MIN_COVERAGE})"
        else:
            reason = "Retrieval quality sufficient"

        return {
            "confidence": confidence,
            "should_answer": should_answer,
            "reason": reason,
            "metrics": {
                "avg_similarity": round(avg_sim, 4),
                "top_similarity": round(top_sim, 4),
                "coverage": round(coverage, 4),
                "result_count": len(results),
            }
        }

    def _calculate_coverage(self, query: str, results: list[dict]) -> float:
        """Calculate what fraction of query terms appear in results."""
        query_terms = set(query.lower().split())
        if not query_terms:
            return 1.0

        # Collect all terms from results
        result_terms = set()
        for r in results:
            text = r.get("clause", "").lower()
            result_terms.update(text.split())

        # Calculate coverage
        matched = query_terms & result_terms
        return len(matched) / len(query_terms)


class FallbackHandler:
    """
    Handles low-confidence retrievals with graceful fallback strategies.
    """

    def __init__(self):
        self.scorer = ConfidenceScorer()

    async def handle(
        self,
        query: str,
        results: list[dict],
        original_answer: str | None = None,
    ) -> dict:
        """
        Handle low-confidence retrieval.

        Returns:
            Dict with fallback strategy and response.
        """
        score = self.scorer.score_retrieval(query, results)

        if score["should_answer"]:
            return {
                "status": "success",
                "confidence": score["confidence"],
                "answer": original_answer,
                "sources": results,
                "metrics": score["metrics"],
            }

        # Low confidence - provide fallback
        if score["metrics"]["result_count"] == 0:
            return {
                "status": "no_results",
                "confidence": 0.0,
                "answer": "I couldn't find any relevant information in the knowledge base. Please try rephrasing your question or upload relevant documents.",
                "sources": [],
                "metrics": score["metrics"],
            }

        # Some results but low confidence
        return {
            "status": "low_confidence",
            "confidence": score["confidence"],
            "answer": (
                f"I found some potentially relevant information, but I'm not fully confident it answers your question. "
                f"Here's what I found:\n\n{original_answer or ''}\n\n"
                f"You may want to rephrase your question or provide more details."
            ),
            "sources": results,
            "metrics": score["metrics"],
            "warning": score["reason"],
        }


# Singleton
confidence_scorer = ConfidenceScorer()
fallback_handler = FallbackHandler()
