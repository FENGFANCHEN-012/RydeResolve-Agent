"""D70: real data through Ryde's API in shadow mode, and a party's "ask a person" appeal.

The HTTP client is exercised against a fake transport: no network. The dataset mode is the default
and must be untouched by the new settings."""
import json

import httpx
import pytest
from sqlalchemy import select

from src.integrations.ryde_api import RydeAPIClient, RydeAPIError, map_ryde_payload
from src.store.db import AuditEntry, Store

DISPUTE = {
    "dispute": {"dispute_id": "RL-01", "trip_id": "RYDE-RL-001", "dispute_type": "fare_dispute",
                "filed_by": "passenger", "description": "Charged more than the quote."},
    "trip": {"trip_id": "RYDE-RL-001", "estimated_fare": 8.6, "total_fare": 12.1},
    "rider": {"rider_id": "R-1"}, "driver": {"driver_id": "D-1"},
    "chat": [{"sender": "passenger", "message": "Why is it more?"}],
    "expected_outcome": {"verdict": "upheld"},          # an answer key must never reach an agent
    "recommended_ruling": "refund the difference",      # nor someone's analysis
}


def _transport(routes: dict[str, tuple[int, object]]):
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers.get("authorization") == "Bearer k-test"
        key = request.url.path + (f"?{request.url.query.decode()}" if request.url.query else "")
        status, body = routes.get(key, (404, {"detail": "not found"}))
        return httpx.Response(status, json=body)
    return httpx.MockTransport(handler)


def _client(routes):
    return RydeAPIClient(api_key="k-test", base_url="https://ryde.example/v1", mode="http",
                         transport=_transport(routes))


def test_map_renames_ryde_keys_and_keeps_disp002_keys():
    out = map_ryde_payload(DISPUTE)
    assert set(out) >= {"dispute_ticket", "trip_data", "rider_profile", "driver_profile", "chat_logs"}
    assert out["dispute_ticket"]["dispute_id"] == "RL-01"
    already = {"dispute_ticket": {"trip_id": "T-1"}, "trip_data": {"trip_id": "T-1"}}
    assert map_ryde_payload(already) == already
    assert map_ryde_payload({"data": already}) == already


def test_map_refuses_a_payload_without_trip_id():
    with pytest.raises(RydeAPIError):
        map_ryde_payload({"dispute": {"dispute_id": "X"}})
    with pytest.raises(RydeAPIError):
        map_ryde_payload(["not", "a", "dispute"])


@pytest.mark.asyncio
async def test_http_mode_fetches_maps_and_strips_answer_keys():
    api = _client({"/v1/disputes/RYDE-RL-001": (200, {"data": DISPUTE})})
    data = await api.get_order_dataset("RYDE-RL-001")
    assert data["_source"] == "ryde_api:RYDE-RL-001"
    assert data["trip_data"]["total_fare"] == 12.1
    text = json.dumps(data)
    assert "expected_outcome" not in text and "recommended_ruling" not in text
    assert await api.get_full_order_context("RYDE-RL-001") == data


@pytest.mark.asyncio
async def test_http_mode_unknown_order_is_none_and_errors_are_raised():
    api = _client({"/v1/disputes/RYDE-RL-500": (500, {"detail": "boom"})})
    assert await api.get_order_dataset("RYDE-RL-404") is None
    with pytest.raises(RydeAPIError):
        await api.get_order_dataset("RYDE-RL-500")


def test_http_mode_lists_open_disputes_without_answer_keys():
    api = _client({"/v1/disputes?status=open": (200, {"disputes": [DISPUTE, {"dispute": {"dispute_id": "bad"}}]})})
    orders = api.list_orders()
    assert [o["order_id"] for o in orders] == ["RYDE-RL-001"]
    assert orders[0]["dispute_type"] == "fare_dispute" and orders[0]["source"] == "ryde_api:RYDE-RL-001"
    assert "expected_outcome" not in json.dumps(orders)


def test_dataset_mode_is_the_default_and_still_reads_files():
    api = RydeAPIClient()
    assert api.mode == "dataset"
    orders = api.list_orders()
    assert orders and all(o["source"].count("/") == 1 for o in orders)


# -- the appeal ---------------------------------------------------------------

@pytest.fixture
def store(tmp_path):
    return Store(f"sqlite:///{(tmp_path / 'appeal.db').as_posix()}")


def _ruling(store, status="resolved"):
    return store.record_ruling(dispute_id="RL-01", order_id="RYDE-RL-001", dispute_type="fare_dispute",
                               status=status, verdict="dismissed", refund_amount=None, confidence=0.9,
                               rationale="fare matched the quote", policy_refs=[], precedent_ids=[],
                               case_summary="x", pipeline_version="t")


def test_appeal_moves_a_resolved_ruling_into_the_review_queue(store):
    r = _ruling(store)
    assert store.review_queue() == []
    esc = store.request_appeal(r.id, "rider", "The quote in my app was S$8.60.", actor="demo")
    assert esc.source == "party_appeal" and esc.reason.startswith("The rider asked for a person: ")
    queue = store.review_queue()
    assert [q["ruling"].id for q in queue] == [r.id]
    assert queue[0]["ruling"].status == "appealed" and queue[0]["ruling"].refund_amount is None
    assert queue[0]["escalation"].snapshot["appeal"]["previous_status"] == "resolved"
    with store.session() as s:
        assert s.scalars(select(AuditEntry).where(AuditEntry.action == "appeal_requested")).first() is not None
    assert store.verify_audit_chain()[0] is True


def test_appeal_on_an_escalated_ruling_keeps_its_status(store):
    r = _ruling(store, status="escalated_to_human")
    store.request_appeal(r.id, "driver", "I have the receipt.", actor="demo")
    assert store.review_queue()[0]["ruling"].status == "escalated_to_human"


def test_appeal_endpoint_is_open_to_the_demo_code_and_reports_the_run_mode():
    from fastapi.testclient import TestClient
    from src.api import main
    from src.store.db import get_store
    client = TestClient(main.app, headers={"Authorization": "Bearer offline-demo"})
    info = client.get("/api/info").json()
    assert info["run_mode"] == "shadow" and info["data_source"] == "dataset"
    r = _ruling(get_store())
    ok = client.post("/api/appeals", json={"ruling_id": r.id, "party": "rider", "reason": "The quote was S$8.60."})
    assert ok.status_code == 200 and ok.json()["status"] == "appealed"
    assert client.post("/api/appeals", json={"ruling_id": r.id + 99, "party": "rider", "reason": "x"}).status_code == 404
    assert client.post("/api/appeals", json={"ruling_id": r.id, "party": "rider", "reason": " "}).status_code == 400
    assert client.post("/api/appeals", json={"ruling_id": r.id, "party": "lawyer", "reason": "x"}).status_code == 400


def test_appeal_rejects_bad_input(store):
    r = _ruling(store)
    with pytest.raises(ValueError):
        store.request_appeal(r.id, "lawyer", "x", actor="demo")
    with pytest.raises(ValueError):
        store.request_appeal(r.id, "rider", "   ", actor="demo")
    with pytest.raises(KeyError):
        store.request_appeal(r.id + 99, "rider", "x", actor="demo")
