import asyncio

from src.rag import embedding


def test_llm_key_does_not_switch_local_policy_embeddings(monkeypatch):
    monkeypatch.setattr(embedding, "EMBEDDING_PROVIDER", "hash")
    monkeypatch.setattr(embedding.GeminiEmbeddingClient, "is_available", property(lambda self: True))

    manager = embedding.EmbeddingManager()

    async def unexpected_call(text):
        raise AssertionError("Gemini embedding should not be called")

    monkeypatch.setattr(manager.gemini_client, "embed", unexpected_call)
    assert manager.mode == "hash"
    assert asyncio.run(manager.embed("cancellation policy")) == manager.hash_embedding._embed("cancellation policy")


def test_gemini_embeddings_require_explicit_opt_in(monkeypatch):
    monkeypatch.setattr(embedding, "EMBEDDING_PROVIDER", "gemini")
    monkeypatch.setattr(embedding.GeminiEmbeddingClient, "is_available", property(lambda self: True))

    assert embedding.EmbeddingManager().mode == "gemini"

    monkeypatch.setattr(embedding.GeminiEmbeddingClient, "is_available", property(lambda self: False))
    assert embedding.EmbeddingManager().mode == "hash"
