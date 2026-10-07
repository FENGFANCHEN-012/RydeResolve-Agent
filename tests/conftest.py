"""
Shared test setup.

Tests always run against the Gemini code path, whatever LLM_PROVIDER says in a
developer's .env, so fakes that patch the Gemini model keep working and no test
spends Groq quota. Tests for the Groq path set the provider themselves.
Likewise tests use the local ChromaDB backend, never the shared Qdrant index.
"""
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from src import config
from src.core import llm_client as llm_module


@pytest.fixture(autouse=True)
def _force_gemini_provider(monkeypatch, tmp_path):
    monkeypatch.setenv("API_ADMIN_KEY", "offline-admin")
    monkeypatch.setenv("API_DEMO_KEY", "offline-demo")
    monkeypatch.setattr(llm_module, "LLM_PROVIDER", "gemini")
    monkeypatch.setattr(llm_module.llm_client, "api_key", "")
    monkeypatch.setattr(llm_module, "LLM_FALLBACK_PROVIDERS", [])  # a failing fake must not reach a real API
    monkeypatch.setattr(llm_module, "_MIN_INTERVAL_SECONDS", 0.0)
    monkeypatch.setattr(llm_module, "_next_request_at", 0.0)
    monkeypatch.setattr(config, "VECTOR_BACKEND", "chroma")
    # Do not let file-upload regressions alter the developer's local policy index.
    from src.rag import indexer, retriever
    local_client = []
    def test_chroma():
        if not local_client:
            local_client.append(indexer.chromadb.PersistentClient(path=str(tmp_path / "chroma")))
        return local_client[0], "test"
    monkeypatch.setattr(indexer, "_get_chroma_client", test_chroma)
    monkeypatch.setattr(retriever, "_get_chroma_client", test_chroma)
    # No test reaches a real model: a key in .env made the "no LLM" tests call Gemini, so
    # they passed or failed on the model's answer and spent quota. Modules import the key by
    # name, so blank every copy; tests that need a key set a fake one themselves.
    for name, module in list(sys.modules.items()):
        if (name == "src" or name.startswith("src.")) and hasattr(module, "LLM_API_KEY"):
            monkeypatch.setattr(module, "LLM_API_KEY", "")
    # Never read the live precedent index or write rulings to the real record store
    monkeypatch.setenv("PRECEDENTS_ENABLED", "0")
    monkeypatch.setenv("RECORD_RULINGS", "0")
    # Saved traces go to a throwaway database, never data/ryde_resolve.db or a hosted one
    from src.store import db as store_db
    monkeypatch.setenv("STORE_URL", f"sqlite:///{(tmp_path / 'store.db').as_posix()}")
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.setattr(store_db, "_store", None)
