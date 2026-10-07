"""Read-only dependency checks; never call a paid model or rebuild an index."""
import asyncio
import os

from sqlalchemy import text
from src import config


def record_check() -> dict:
    from src.store.db import DEFAULT_URL, _make_engine
    engine = _make_engine(os.getenv("STORE_URL") or os.getenv("DATABASE_URL") or DEFAULT_URL)
    try:
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
        return {"ok": True, "message": "Record store connected."}
    finally:
        engine.dispose()


def policy_check() -> dict:
    if config.VECTOR_BACKEND == "qdrant":
        from qdrant_client import QdrantClient
        from fastembed import TextEmbedding
        client = QdrantClient(url=config.QDRANT_URL, api_key=config.QDRANT_API_KEY or None, timeout=5)
        try:
            info = client.get_collection(config.QDRANT_COLLECTION)
            expected = next((m["dim"] for m in TextEmbedding.list_supported_models()
                             if m["model"] == config.QDRANT_DENSE_MODEL), None)
            vectors = info.config.params.vectors
            dense = vectors.get("dense") if isinstance(vectors, dict) else None
            if not expected or not dense or dense.size != expected:
                return {"ok": False, "message": "Policy collection and embedding model dimensions do not match."}
            count = client.count(config.QDRANT_COLLECTION, exact=True).count
            return {"ok": count > 0, "message": f"{count} policy chunks.",
                    "collection": config.QDRANT_COLLECTION, "backend": "qdrant",
                    "embedding_model": config.QDRANT_DENSE_MODEL}
        finally:
            client.close()
    from src.rag.indexer import DocumentIndexer
    indexer = DocumentIndexer()
    stats = indexer.get_collection_stats()
    return {"ok": stats.get("chunk_count", 0) > 0,
            "message": f"{stats.get('chunk_count', 0)} policy chunks.",
            "collection": stats.get("collection"), "backend": stats.get("mode")}


async def _bounded_check(name, check):
    try:
        return name, await asyncio.wait_for(asyncio.to_thread(check), timeout=8)
    except ModuleNotFoundError:
        return name, {"ok": False, "message": "A required package is missing. Install requirements.txt in the server's Python environment."}
    except asyncio.TimeoutError:
        return name, {"ok": False, "message": "The connection check timed out."}
    except Exception:
        # Connection exception strings may contain credentials or internal host names.
        return name, {"ok": False, "message": "Could not connect. Check the server configuration."}


async def check_readiness() -> dict:
    from src.core.llm_client import LLMClient
    try:
        llm = LLMClient()
        llm_status = {"ok": bool(llm.api_key), "provider": llm.provider, "model": llm.model,
                      "message": "Model key configured; availability and quota require a live run." if llm.api_key
                      else "The selected model provider has no API key."}
    except ValueError:
        llm_status = {"ok": False, "message": "Unsupported model provider."}
    checks = dict(await asyncio.gather(_bounded_check("records", record_check),
                                       _bounded_check("policies", policy_check)))
    checks["model"] = llm_status
    return {"status": "ready" if all(c["ok"] for c in checks.values()) else "needs_setup", "checks": checks}
