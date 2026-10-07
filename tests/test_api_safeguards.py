"""API boundary regressions, with isolated records and no model/index network calls."""
import asyncio
import io
from pathlib import Path

import httpx
import pytest
from fastapi import HTTPException, UploadFile
from fastapi.testclient import TestClient

from src.api import main
from src.api import readiness, uploads


def admin():
    return TestClient(main.app, headers={"Authorization": "Bearer offline-admin"})


def test_unauthenticated_api_cannot_read_or_modify():
    client = TestClient(main.app)
    assert client.get("/api/disputes/cases").status_code == 401
    assert client.delete("/api/rag/collection").status_code == 401
    assert client.get("/api/health").status_code == 200
    assert client.get("/").headers["content-type"].startswith("text/html")
    assert client.get("/.env").status_code == 404


def test_demo_credentials_cannot_impersonate_an_admin():
    client = TestClient(main.app, headers={"Authorization": "Bearer offline-demo"})
    assert client.get("/api/disputes/cases").status_code == 200
    assert client.get("/api/flags").status_code == 403
    assert client.post("/api/flags", json={"reviewer": "admin"}).status_code == 403
    assert client.delete("/api/rag/collection").status_code == 403


@pytest.mark.asyncio
async def test_loopback_only_without_access_codes_blocks_rebinding_and_foreign_origin(monkeypatch):
    monkeypatch.delenv("API_ADMIN_KEY")
    monkeypatch.delenv("API_DEMO_KEY")
    transport = httpx.ASGITransport(app=main.app, client=("127.0.0.1", 54321))
    async with httpx.AsyncClient(transport=transport, base_url="http://127.0.0.1:8000") as client:
        assert (await client.get("/api/disputes/cases")).status_code == 200
        assert (await client.get("/api/disputes/cases", headers={"Host":"evil.example"})).status_code == 503
        assert (await client.get("/api/disputes/cases", headers={"Origin":"https://evil.example"})).status_code == 403
    remote = httpx.ASGITransport(app=main.app, client=("192.0.2.1", 54321))
    async with httpx.AsyncClient(transport=remote, base_url="http://127.0.0.1:8000") as client:
        assert (await client.get("/api/disputes/cases")).status_code == 503


def test_audit_actor_comes_from_authenticated_session(monkeypatch):
    from src.store import people
    seen = []
    def record(*args, **kwargs):
        seen.append(kwargs["raised_by"])
        return object()
    monkeypatch.setattr(people, "raise_flag", record)
    monkeypatch.setattr(main, "_flag_json", lambda flag: {"ok": True})
    response = admin().post("/api/flags", json={"user_id":"R1", "signal":"x", "detail":"x", "raised_by":"forged"})
    assert response.status_code == 200
    assert seen == ["admin"]


@pytest.mark.parametrize("filename", ["../escape.txt", "..\\escape.txt", "C:escape.txt", "x.exe", "x\x00.txt"])
def test_unsafe_upload_names_rejected_before_indexing(filename):
    response = admin().post("/api/rag/upload", files={"file":(filename,b"test","text/plain")})
    assert response.status_code == 400


@pytest.mark.asyncio
async def test_upload_size_is_bounded(monkeypatch):
    monkeypatch.setattr(uploads, "MAX_FILE_BYTES", 100)
    with pytest.raises(HTTPException) as error:
        await uploads.read_upload(UploadFile(filename="x.txt", file=io.BytesIO(b"x" * 101)))
    assert error.value.status_code == 413


def test_upload_count_limit_rejects_before_indexing():
    response = admin().post("/api/rag/upload-multiple", files=[("files", (f"{i}.txt", b"x")) for i in range(6)])
    assert response.status_code == 413


@pytest.mark.asyncio
async def test_chunked_multipart_is_bounded_before_parsing_to_disk(monkeypatch):
    monkeypatch.setattr(uploads, "MAX_FILE_BYTES", 10)
    async def body():
        yield b'--bound\r\nContent-Disposition: form-data; name="file"; filename="x.txt"\r\n\r\n'
        yield b'x' * 70000
        yield b'\r\n--bound--\r\n'
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=main.app), base_url="http://test",
                                headers={"Authorization":"Bearer offline-admin"}) as client:
        response = await client.post("/api/rag/upload", content=body(),
                                     headers={"Content-Type":"multipart/form-data; boundary=bound"})
    assert response.status_code == 413


def test_official_policy_index_cannot_be_deleted_or_contaminated():
    response = admin().delete("/api/rag/collection?collection_name=ryde_policies_official")
    assert response.status_code == 403
    response = admin().post("/api/rag/upload?collection_name=ryde_policies_official",
                            files={"file":("x.txt",b"untrusted")})
    assert response.status_code == 403


def test_invalid_order_path_and_extension_are_rejected():
    response = admin().post("/api/disputes/resolve-with-files?order_id=..%2Fescape&report_text=x",
                           files={"evidence_files":("x.png", b"x")})
    assert response.status_code == 400
    response = admin().post("/api/disputes/resolve-with-files?order_id=ORDER-1&report_text=x",
                           files={"evidence_files":("x.exe", b"x")})
    assert response.status_code == 400


def test_generated_upload_paths_are_unique_and_contained(tmp_path):
    a, b = uploads.upload_path(tmp_path, ".txt"), uploads.upload_path(tmp_path, ".txt")
    assert a != b and a.parent == b.parent == tmp_path


def test_failed_readiness_is_explicit_and_hides_credentials(monkeypatch):
    def fail():
        raise RuntimeError("postgresql://secret:password@private/db")
    monkeypatch.setattr(readiness, "record_check", fail)
    monkeypatch.setattr(readiness, "policy_check", lambda: {"ok":True, "message":"Ready"})
    response = admin().get("/api/readiness")
    assert response.status_code == 503
    assert not response.json()["checks"]["records"]["ok"]
    assert "password" not in response.text and "secret" not in response.text


@pytest.mark.asyncio
async def test_stream_error_always_finishes_and_reports_unsaved_trace(monkeypatch):
    async def fail(*args, **kwargs):
        raise RuntimeError("offline failure")
    monkeypatch.setattr(main.Orchestrator, "resolve", fail)
    monkeypatch.setattr(main, "_save_trace", lambda *args: None)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=main.app), base_url="http://test",
                                headers={"Authorization":"Bearer offline-admin"}) as client:
        response = await client.post("/api/disputes/resolve-stream", json={"order_id":"A"})
    assert response.status_code == 200
    assert '"type": "error"' in response.text and '"type": "done"' in response.text
    assert '"trace_saved": false' in response.text
    assert main._active_runs == 0


@pytest.mark.asyncio
async def test_concurrent_reviews_rejected_and_slot_released(monkeypatch):
    entered, finish = asyncio.Event(), asyncio.Event()
    async def resolve(*args, **kwargs):
        entered.set()
        await finish.wait()
        return {"status":"resolved"}
    monkeypatch.setattr(main.Orchestrator, "resolve", resolve)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=main.app), base_url="http://test",
                                headers={"Authorization":"Bearer offline-admin"}) as client:
        first = asyncio.create_task(client.post("/api/disputes/resolve", json={"order_id":"A"}))
        await asyncio.wait_for(entered.wait(), 5)
        second = await client.post("/api/disputes/resolve", json={"order_id":"B"})
        assert second.status_code == 409
        finish.set()
        assert (await first).status_code == 200
        assert main._active_runs == 0
