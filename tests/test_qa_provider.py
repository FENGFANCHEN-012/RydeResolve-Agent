"""RAG pages must use the selected provider and include readable source text."""
from types import SimpleNamespace
from unittest.mock import AsyncMock
import pytest
from src.rag import qa_engine, advanced_qa_engine

CHUNK = {"source":"official.md", "similarity":0.016, "chunk_index":0, "clause":"Policy source text"}


@pytest.mark.asyncio
@pytest.mark.parametrize("advanced", [False, True])
async def test_rag_uses_non_gemini_key_and_returns_source_clause(monkeypatch, advanced):
    model = SimpleNamespace(api_key="offline-groq-key", chat=AsyncMock(return_value="Grounded answer"))
    module = advanced_qa_engine if advanced else qa_engine
    monkeypatch.setattr(module, "llm_client", model)
    if advanced:
        monkeypatch.setattr(module.advanced_retriever, "retrieve", AsyncMock(return_value={
            "results":[CHUNK], "confidence":.9, "should_answer":True, "metrics":{}, "query_variants":["q"]}))
        engine = module.AdvancedRAGQAEngine()
    else:
        engine = module.RAGQAEngine.__new__(module.RAGQAEngine)
        engine.retriever = SimpleNamespace(retrieve=lambda **kwargs: [CHUNK])
    result = await engine.answer("q")
    assert result["answer"] == "Grounded answer"
    assert result["sources"][0]["clause"] == CHUNK["clause"]
    model.chat.assert_awaited_once()
