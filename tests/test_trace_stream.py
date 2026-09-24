"""
Tests for the pipeline trace + /api/disputes/resolve-stream (no real LLM calls).
"""
import json
import os
import sys

import httpx
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from fastapi.testclient import TestClient

from src.api import main as api_main
from src.core import llm_client as llm_module
from src.core.trace import Tracer, record_llm_call, set_tracer, step

FAKE_REPLY = json.dumps({
    "stance": "Driver waited the full window.", "evidence": ["GPS stationary 08:43-08:51"],
    "contradictory_evidence": [], "missing_evidence": [], "obligations": [],
    "remedy_requested": "none", "policy_references": [], "reasoning": "Evidence supports the driver.",
    "confidence": 0.8, "requires_human_review": False,
    "passenger_compliant": False, "driver_compliant": True, "violations": [],
    "verdict": "dismissed", "rationale": "Driver followed the no-show procedure.",
    "refund_amount": None, "compensation": None, "driver_penalty": None,
    "escalation_recommended": False, "human_review_needed": False,
})


class _FakeChat:
    def send_message(self, prompt, generation_config=None):
        return type("R", (), {"text": FAKE_REPLY})()


class _FakeModel:
    def start_chat(self, history=None):
        return _FakeChat()


@pytest.fixture
def fake_llm(monkeypatch, tmp_path):
    monkeypatch.setattr(llm_module.LLMClient, "_get_model", lambda self: _FakeModel())
    monkeypatch.setattr(api_main, "TRACES_DIR", str(tmp_path))


@pytest.mark.asyncio
async def test_step_is_noop_without_tracer():
    async with step("X", "no tracer") as s:
        s["output"] = 1
    record_llm_call("p", "r", 1)  # must not raise


@pytest.mark.asyncio
async def test_llm_call_attached_to_running_step():
    tracer = Tracer()
    set_tracer(tracer)
    try:
        async with step("Agent", "title", {"a": 1}) as s:
            record_llm_call("prompt", "resp", 5)
            s["output"] = {"ok": True}
    finally:
        set_tracer(None)
    types = [e["type"] for e in tracer.events]
    assert types == ["step_start", "llm_call", "step_end"]
    assert tracer.events[1]["step_id"] == tracer.events[0]["id"]
    assert tracer.events[2]["output"] == {"ok": True}


async def _stream_events(body):
    """Run the SSE endpoint in-process (same event loop) and parse its events."""
    transport = httpx.ASGITransport(app=api_main.app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        r = await client.post("/api/disputes/resolve-stream", json=body, timeout=60)
    assert r.status_code == 200
    return [json.loads(line[6:]) for line in r.text.splitlines() if line.startswith("data: ")]


@pytest.mark.asyncio
async def test_stream_full_run_disp002(fake_llm, tmp_path):
    events = await _stream_events({"order_id": "TRIP-2026-09945"})
    types = [e["type"] for e in events]

    assert types[0] == "run_start" and types[-1] == "done"
    assert "result" in types and "error" not in types

    agents = [e["agent"] for e in events if e["type"] == "step_end"]
    assert agents[:2] == ["Collector", "Classifier"]
    assert {"Passenger", "Driver", "Policy", "Arbitrator", "Fairness"} <= set(agents)
    # Fairness audits the decision after the Arbitrator, before any execution
    assert agents.index("Fairness") > agents.index("Arbitrator")
    result = next(e["result"] for e in events if e["type"] == "result")
    if result["status"] == "resolved":
        assert agents[-1] == "Executor"
    else:
        assert "Executor" not in agents

    # Every step_start has a matching step_end
    starts = {e["id"] for e in events if e["type"] == "step_start"}
    ends = {e["id"] for e in events if e["type"] == "step_end"}
    assert starts == ends

    # LLM calls carry the exact prompt and belong to a step
    calls = [e for e in events if e["type"] == "llm_call"]
    assert calls and all(c["step_id"] in starts and c["prompt"] for c in calls)

    # The answer key never appears anywhere in the stream. (The agents' system
    # prompts do mention the word 'expected_outcome' as a field to ignore.)
    dumped = json.dumps(events).lower()
    assert '"expected_outcome":' not in dumped
    assert "expected ruling" not in dumped

    # Saved for replay
    saved = events[-1]["trace_name"]
    assert saved and (tmp_path / saved).exists()


def test_cases_endpoint_lists_datasets_without_answers():
    r = TestClient(api_main.app).get("/api/disputes/cases")
    cases = r.json()["cases"]
    ids = {c["order_id"] for c in cases}
    assert {"RYDE-DEMO-001", "RYDE-DEMO-003", "TRIP-2026-09945"} <= ids
    assert "expected" not in r.text.lower()


def test_trace_name_is_validated():
    r = TestClient(api_main.app).get("/api/disputes/traces/..%2F..%2Fsecret.json")
    assert r.status_code in (400, 404)


@pytest.mark.asyncio
async def test_retrieval_attached_to_running_step():
    from src.core.trace import record_retrieval
    tracer = Tracer()
    set_tracer(tracer)
    try:
        async with step("Policy", "check") as s:
            record_retrieval("fare_dispute", [{"source": "Guide", "section": "Scenario 3", "similarity": 0.4,
                                               "chunk_index": 2, "clause": "text"}])
            s["output"] = {}
    finally:
        set_tracer(None)
    ev = tracer.events[1]
    assert ev["type"] == "retrieval" and ev["step_id"] == tracer.events[0]["id"]
    assert ev["clauses"][0]["section"] == "Scenario 3"
    assert ev["clauses"][0]["reference"] == "Guide#2"


@pytest.mark.asyncio
async def test_case_detail_separates_answer_key():
    transport = httpx.ASGITransport(app=api_main.app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        r = await client.get("/api/disputes/cases/RYDE-DEMO-003")
        missing = await client.get("/api/disputes/cases/NOPE-1")
    body = r.json()
    assert r.status_code == 200 and missing.status_code == 404
    assert "expected_outcome" not in json.dumps(body["dataset"])  # what agents get
    assert body["expected_outcome"]["verdict"] == "upheld"       # shown only in the UI
