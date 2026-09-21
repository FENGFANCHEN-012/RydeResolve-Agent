"""
Advanced RAG QA Engine
Uses the full retrieval pipeline with confidence scoring and fallback handling.
"""
from src.rag.advanced_retriever import advanced_retriever
from src.rag.confidence_scorer import fallback_handler
from src.core.llm_client import llm_client
from src.config import LLM_API_KEY


class AdvancedRAGQAEngine:
    """
    Production RAG QA with advanced retrieval and quality control.
    """

    RAG_PROMPT_TEMPLATE = """You are a helpful assistant answering questions based on retrieved documents.

Below are relevant document excerpts retrieved from the knowledge base:

--- RETRIEVED CONTEXT ---
{context}
--- END CONTEXT ---

Based on the above context, answer the following question. If the context does not contain enough information to answer, say so clearly. Cite source filenames when referencing specific information.

Question: {question}

Answer:"""

    async def answer(
        self,
        question: str,
        top_k: int = 5,
        collection_name: str | None = None,
        temperature: float = 0.3,
    ) -> dict:
        """
        Answer a question using advanced RAG pipeline.

        Returns:
            {
                "answer": str,
                "sources": list,
                "question": str,
                "confidence": float,
                "should_answer": bool,
                "metrics": dict,
                "query_variants": list[str],
            }
        """
        # 1. Advanced retrieval
        retrieval = await advanced_retriever.retrieve(
            query=question,
            top_k=top_k,
            collection_name=collection_name,
        )

        chunks = retrieval["results"]
        confidence = retrieval["confidence"]
        should_answer = retrieval["should_answer"]
        metrics = retrieval["metrics"]
        query_variants = retrieval["query_variants"]

        if not chunks:
            return {
                "answer": "I couldn't find any relevant documents in the knowledge base. Please upload some documents first.",
                "sources": [],
                "question": question,
                "confidence": 0.0,
                "should_answer": False,
                "metrics": metrics,
                "query_variants": query_variants,
            }

        # 2. Assemble context
        context_parts = []
        for i, chunk in enumerate(chunks, 1):
            context_parts.append(
                f"[{i}] Source: {chunk['source']}\n"
                f"    {chunk['clause'][:800]}"
            )
        context = "\n\n".join(context_parts)

        # 3. Generate answer via LLM (or fallback if low confidence)
        if not LLM_API_KEY:
            answer_text = "LLM API key not configured."
        elif not should_answer:
            # Low confidence - use fallback
            fallback = await fallback_handler.handle(question, chunks)
            answer_text = fallback["answer"]
        else:
            prompt = self.RAG_PROMPT_TEMPLATE.format(
                context=context,
                question=question,
            )
            messages = [{"role": "user", "content": prompt}]
            answer_text = await llm_client.chat(
                messages=messages,
                temperature=temperature,
            )

        # 4. Format sources
        sources = [
            {
                "source": chunk["source"],
                "similarity": chunk.get("similarity", 0),
                "rerank_score": chunk.get("rerank_score", 0),
                "combined_score": chunk.get("combined_score", chunk.get("similarity", 0)),
                "chunk_index": chunk.get("chunk_index", 0),
                "preview": chunk["clause"][:200] + "..." if len(chunk["clause"]) > 200 else chunk["clause"],
            }
            for chunk in chunks
        ]

        return {
            "answer": answer_text,
            "sources": sources,
            "question": question,
            "confidence": confidence,
            "should_answer": should_answer,
            "metrics": metrics,
            "query_variants": query_variants,
        }


# Singleton
advanced_rag_qa_engine = AdvancedRAGQAEngine()
