"""
RAG Question-Answering Engine
Combines document retrieval with LLM generation to produce grounded answers.

Flow: User question → Vector search (ChromaDB) → Context assembly → LLM answer
"""
from src.rag.retriever import DocumentRetriever
from src.core.llm_client import llm_client
from src.config import LLM_API_KEY


class RAGQAEngine:
    """
    Retrieval-Augmented Generation QA engine.
    Retrieves relevant chunks from vector DB, then feeds context to LLM for answer.
    """

    RAG_PROMPT_TEMPLATE = """You are a helpful assistant answering questions based on retrieved documents.

Below are relevant document excerpts retrieved from the knowledge base:

--- RETRIEVED CONTEXT ---
{context}
--- END CONTEXT ---

Based on the above context, answer the following question. If the context does not contain enough information to answer, say so clearly. Cite source filenames when referencing specific information.

Question: {question}

Answer:"""

    def __init__(self):
        self.retriever = DocumentRetriever()

    async def answer(
        self,
        question: str,
        top_k: int = 5,
        collection_name: str | None = None,
        temperature: float = 0.3,
    ) -> dict:
        """
        Answer a question using RAG.

        Args:
            question: User's natural language question
            top_k: Number of chunks to retrieve
            collection_name: Optional specific collection to search
            temperature: LLM temperature

        Returns:
            {
                "answer": str,
                "sources": list of {source, similarity, chunk_index, preview},
                "question": str,
            }
        """
        # 1. Retrieve relevant chunks
        chunks = self.retriever.retrieve(
            query=question,
            top_k=top_k,
            collection_name=collection_name,
        )

        if not chunks:
            return {
                "answer": "I couldn't find any relevant documents in the knowledge base. Please upload some documents first.",
                "sources": [],
                "question": question,
            }

        # 2. Assemble context
        context_parts = []
        for i, chunk in enumerate(chunks, 1):
            context_parts.append(
                f"[{i}] Source: {chunk['source']}\n"
                f"    {chunk['clause'][:800]}"
            )
        context = "\n\n".join(context_parts)

        # 3. Generate answer via LLM
        if not LLM_API_KEY:
            # No LLM key configured — return retrieved context directly
            context_summary = "\n\n".join(
                f"[{i+1}] Source: {chunk['source']} (similarity: {chunk['similarity']:.2%})\n    {chunk['clause'][:500]}"
                for i, chunk in enumerate(chunks)
            )
            answer_text = (
                f"LLM API key not configured. Here are the most relevant chunks found:\n\n{context_summary}"
            )
        else:
            prompt = self.RAG_PROMPT_TEMPLATE.format(
                context=context,
                question=question,
            )

            messages = [
                {"role": "user", "content": prompt},
            ]

            answer_text = await llm_client.chat(
                messages=messages,
                temperature=temperature,
            )

        # 4. Format sources for response
        sources = [
            {
                "source": chunk["source"],
                "similarity": chunk["similarity"],
                "chunk_index": chunk["chunk_index"],
                "preview": chunk["clause"][:200] + "..." if len(chunk["clause"]) > 200 else chunk["clause"],
            }
            for chunk in chunks
        ]

        return {
            "answer": answer_text,
            "sources": sources,
            "question": question,
        }


# Singleton
rag_qa_engine = RAGQAEngine()
