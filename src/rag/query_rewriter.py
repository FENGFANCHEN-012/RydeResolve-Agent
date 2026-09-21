"""
Query Rewriting for RAG
Uses LLM to expand user queries into multiple search-friendly variants.
Improves recall by capturing synonyms, related concepts, and implicit intent.
"""
import asyncio
from src.core.llm_client import llm_client


QUERY_REWRITE_PROMPT = """Generate 3 search queries for: {question}

Return exactly 3 lines, each starting with a number:
1. first query
2. second query  
3. third query"""


class QueryRewriter:
    """Rewrites user queries into multiple search variants using LLM."""

    async def rewrite(self, question: str, max_variants: int = 4) -> list[str]:
        """
        Generate search query variants from user question.

        Returns:
            List of query strings, including the original question.
        """
        try:
            messages = [
                {"role": "user", "content": QUERY_REWRITE_PROMPT.format(question=question)},
            ]
            response = await llm_client.chat(
                messages=messages,
                temperature=0.2,
                max_tokens=512,
            )

            # Parse numbered list from response
            variants = []
            for line in response.strip().split("\n"):
                line = line.strip()
                # Match "1. query text" or "- query text" or "* query text"
                if line and (line[0].isdigit() or line.startswith(("-", "*"))):
                    # Remove prefix
                    text = line
                    if "." in text[:3]:
                        text = text.split(".", 1)[1]
                    elif text.startswith(("-", "*")):
                        text = text[1:]
                    text = text.strip().strip('"').strip("'")
                    if text and len(text) > 3:
                        variants.append(text)

            if variants:
                # Deduplicate and include original
                all_queries = [question] + [v for v in variants if v.lower() != question.lower()]
                seen = set()
                deduped = []
                for q in all_queries:
                    q_lower = q.lower().strip()
                    if q_lower not in seen:
                        seen.add(q_lower)
                        deduped.append(q.strip())
                return deduped[:max_variants]
        except Exception as e:
            print(f"Query rewrite failed: {e}")

        return [question]


# Singleton
query_rewriter = QueryRewriter()
