"""
Re-ranker: Cross-encoder style re-ranking using LLM
Reranks retrieved chunks by relevance to the query for better precision.
"""
import asyncio
from src.core.llm_client import llm_client


RERANK_PROMPT = """Rate how relevant each document excerpt is to answering the question.
Score from 0 (completely irrelevant) to 10 (perfectly answers the question).

Question: {question}

Documents:
{documents}

Output ONLY a JSON array of scores: [score1, score2, ...]
Do not include any other text."""


class LLMReranker:
    """
    Uses LLM to re-rank retrieved documents by relevance.
    More accurate than pure vector similarity for final ranking.
    """

    BATCH_SIZE = 5  # Number of docs to rerank at once

    async def rerank(
        self,
        query: str,
        documents: list[dict],
        top_k: int = 5,
    ) -> list[dict]:
        """
        Re-rank documents by LLM relevance scoring.

        Args:
            query: User question
            documents: Retrieved document chunks
            top_k: Number of top results to return

        Returns:
            Re-ranked and filtered documents
        """
        if not documents:
            return []

        # Score documents in batches
        all_scores = []
        for i in range(0, len(documents), self.BATCH_SIZE):
            batch = documents[i:i + self.BATCH_SIZE]
            scores = await self._score_batch(query, batch)
            all_scores.extend(scores)

        # Attach scores and sort
        for doc, score in zip(documents, all_scores):
            doc["rerank_score"] = score
            # Combined score: vector similarity + rerank score
            doc["combined_score"] = round(
                doc.get("similarity", 0) * 0.4 + (score / 10.0) * 0.6,
                4
            )

        # Sort by combined score descending
        ranked = sorted(documents, key=lambda x: x["combined_score"], reverse=True)

        # Filter out low-relevance results (score < 3/10)
        filtered = [d for d in ranked if d.get("rerank_score", 0) >= 2.0]

        return filtered[:top_k] if filtered else ranked[:top_k]

    async def _score_batch(self, query: str, batch: list[dict]) -> list[float]:
        """Score a batch of documents using LLM."""
        try:
            docs_text = "\n".join(
                f"[{i+1}] {doc['clause'][:300]}..."
                for i, doc in enumerate(batch)
            )

            messages = [
                {"role": "user", "content": RERANK_PROMPT.format(
                    question=query,
                    documents=docs_text,
                )},
            ]

            response = await llm_client.chat(
                messages=messages,
                temperature=0.1,
                max_tokens=128,
            )

            # Parse JSON array
            import json
            text = response.strip()
            if "[" in text and "]" in text:
                start = text.index("[")
                end = text.rindex("]") + 1
                text = text[start:end]

            scores = json.loads(text)
            if isinstance(scores, list) and len(scores) == len(batch):
                return [float(s) for s in scores]

        except Exception as e:
            print(f"Rerank scoring failed: {e}")

        # Fallback: return middle scores
        return [5.0] * len(batch)


class SimpleReranker:
    """
    Lightweight reranker using heuristics (no LLM call).
    Boosts scores for documents containing query keywords.
    """

    def rerank(self, query: str, documents: list[dict], top_k: int = 5) -> list[dict]:
        """Re-rank using keyword overlap heuristics."""
        query_terms = set(query.lower().split())

        for doc in documents:
            doc_text = doc.get("clause", "").lower()
            # Count query term matches
            matches = sum(1 for term in query_terms if term in doc_text)
            overlap_score = matches / max(len(query_terms), 1)

            # Boost similarity with keyword overlap
            base_sim = doc.get("similarity", 0)
            doc["rerank_score"] = round(overlap_score * 10, 2)
            doc["combined_score"] = round(base_sim * 0.6 + overlap_score * 0.4, 4)

        ranked = sorted(documents, key=lambda x: x["combined_score"], reverse=True)
        return ranked[:top_k]


# Singleton
llm_reranker = LLMReranker()
simple_reranker = SimpleReranker()
