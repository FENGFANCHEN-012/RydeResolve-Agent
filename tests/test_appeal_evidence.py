"""D73: a party adds new evidence to a borderline auto-resolved ruling; the AI settles it first and a
person sees only what the AI cannot settle. Also the party-facing status endpoint."""
import json

import pytest

from src.store.db import Store


@pytest.fixture
def store(tmp_path):
    return Store(f"sqlite:///{(tmp_path / 'appeal73.db').as_posix()}")


def _ruling(store, status="resolved", confidence=0.72, verdict="dismissed", refund=None):
    return store.record_ruling(dispute_id="RL-01", order_id="RYDE-RL-001", dispute_type="fare_dispute",
                               status=status, verdict=verdict, refund_amount=refund, confidence=confidence,
                               rationale="fare matched the quote", policy_refs=[], precedent_ids=[],
                               case_summary="x", pipeline_version="t")


class _LLM:
    def __init__(self, answer):
        self.answer, self.calls = answer, 0

    async def chat_json(self, **_):
        self.calls += 1
        if isinstance(self.answer, Exception):
            raise self.answer
        return json.dumps(self.answer)


def _rerun(result):
    calls = []

    async def run(ruling, appeal):
        calls.append(appeal.evidence)
        return result(ruling) if callable(result) else result
    run.calls = calls
    return run


def _second(store, confidence, verdict="dismissed", refund=None, status="resolved"):
    def make(_ruling_unused):
        new = _ruling(store, status=status, confidence=confidence, verdict=verdict, refund=refund)
        make.new = new
        return {"ruling_id": new.id, "status": status,
                "verdict": {"verdict": verdict, "refund_amount": refund, "confidence": confidence}}
    return make


NEW_FACT = {"new_fact": True, "facts": ["receipt S$12.40"], "why": "A receipt amount."}


def test_appeal_opens_only_on_a_borderline_auto_resolved_ruling(store):
    assert store.open_appeal(_ruling(store, confidence=0.79).id, "rider", "Receipt S$8.60", "demo").status == "checking"
    assert store.open_appeal(_ruling(store, confidence=None).id, "rider", "Receipt S$8.60", "demo")
    for r in (_ruling(store, confidence=0.80), _ruling(store, confidence=0.9),
              _ruling(store, status="escalated_to_human", confidence=0.4)):
        with pytest.raises(ValueError, match="not open"):
            store.open_appeal(r.id, "rider", "Receipt S$8.60", "demo")
    r = _ruling(store)
    store.open_appeal(r.id, "driver", "I waited 12 minutes", "demo")
    # once per ruling, whichever party asks
    for party in ("driver", "rider"):
        with pytest.raises(ValueError, match="already"):
            store.open_appeal(r.id, party, "another try", "demo")


def test_appeal_rejects_bad_input(store):
    r = _ruling(store)
    with pytest.raises(ValueError):
        store.open_appeal(r.id, "lawyer", "x", actor="demo")
    with pytest.raises(ValueError):
        store.open_appeal(r.id, "rider", "   ", actor="demo")
    with pytest.raises(KeyError):
        store.open_appeal(r.id + 99, "rider", "x", actor="demo")


@pytest.mark.asyncio
async def test_disagreeing_alone_keeps_the_decision_without_a_person(store):
    from src.core.appeal import settle
    r = _ruling(store)
    a = store.open_appeal(r.id, "rider", "This is unfair, I want my money back", "demo")
    rerun = _rerun({})
    out = await settle(a.id, store, _LLM({"new_fact": False, "facts": [], "why": "It repeats the complaint."}), rerun)
    assert out.status == "kept" and "does not add information" in out.note and rerun.calls == []
    assert store.review_queue() == []
    status = store.case_status(r.id)
    assert status["final"]["by"] == "ai" and not status["with_person"] and not status["appeal_open"]


@pytest.mark.asyncio
async def test_a_new_fact_is_decided_again_and_a_confident_second_ruling_stands(store):
    from src.core.appeal import settle
    r = _ruling(store)
    a = store.open_appeal(r.id, "rider", "My receipt shows S$12.40, not the S$8.60 quote", "demo")
    rerun = _rerun(_second(store, 0.95, verdict="upheld", refund=3.8))
    out = await settle(a.id, store, _LLM(NEW_FACT), rerun)
    assert out.status == "changed" and out.new_ruling_id and rerun.calls
    assert store.review_queue() == []
    final = store.case_status(r.id)["final"]
    assert (final["verdict"], final["refund_amount"], final["by"]) == ("upheld", 3.8, "ai")


@pytest.mark.asyncio
async def test_same_outcome_after_a_new_fact_is_kept(store):
    from src.core.appeal import settle
    r = _ruling(store)
    a = store.open_appeal(r.id, "rider", "The driver took Lornie Road", "demo")
    out = await settle(a.id, store, _LLM(NEW_FACT), _rerun(_second(store, 0.97)))
    assert out.status == "kept" and "stays the same" in out.note


@pytest.mark.asyncio
async def test_still_unsure_after_the_new_fact_goes_to_a_person(store):
    from src.core.appeal import settle
    r = _ruling(store)
    a = store.open_appeal(r.id, "driver", "The rider was not at the pickup, I have a photo", "demo")
    second = _second(store, 0.78)
    out = await settle(a.id, store, _LLM(NEW_FACT), _rerun(second))
    assert out.status == "with_person"
    assert [q["ruling"].id for q in store.review_queue()] == [second.new.id]
    status = store.case_status(r.id)
    assert status["with_person"] and status["final"] is None


@pytest.mark.asyncio
async def test_a_second_ruling_the_pipeline_escalated_is_not_queued_twice(store):
    from src.core.appeal import settle
    r = _ruling(store)
    a = store.open_appeal(r.id, "rider", "Receipt S$12.40", "demo")
    second = _second(store, 0.6, status="escalated_to_human")
    out = await settle(a.id, store, _LLM(NEW_FACT), _rerun(second))
    assert out.status == "with_person" and out.new_ruling_id == second.new.id
    assert [q["ruling"].id for q in store.review_queue()] == [second.new.id]


@pytest.mark.asyncio
async def test_safety_wording_goes_straight_to_a_person_without_the_ai(store):
    from src.core.appeal import settle
    r = _ruling(store)
    a = store.open_appeal(r.id, "rider", "He touched me when I got out, that is why I left early", "demo")
    llm, rerun = _LLM({"new_fact": False}), _rerun({})
    out = await settle(a.id, store, llm, rerun)
    assert out.status == "with_person" and llm.calls == 0 and rerun.calls == []
    assert [q["ruling"].id for q in store.review_queue()] == [r.id]


@pytest.mark.asyncio
async def test_an_ai_failure_hands_the_case_to_a_person(store):
    from src.core.appeal import settle
    r = _ruling(store)
    a = store.open_appeal(r.id, "rider", "Receipt S$12.40", "demo")
    out = await settle(a.id, store, _LLM(RuntimeError("provider down")), _rerun({}))
    assert out.status == "with_person"
    assert [q["ruling"].id for q in store.review_queue()] == [r.id]
    assert store.verify_audit_chain()[0] is True


def test_notice_invites_new_evidence_only_on_a_borderline_ruling():
    from src.agents.executor import _NOTIFICATION_TEMPLATES
    for lang, t in _NOTIFICATION_TEMPLATES.items():
        assert "{appeal}" in t["message"] and t["appeal"], lang
        assert t["message"].format(dispute_id="D", recipient_label="R", rationale_summary="r", outcome="o",
                                   appeal="").count(t["appeal"].strip()) == 0


def test_appeal_and_status_endpoints(monkeypatch):
    from fastapi.testclient import TestClient
    import src.core.appeal as appeal_mod
    from src.api import main
    from src.store.db import get_store

    async def no_settle(appeal_id, *a, **k):
        return None
    monkeypatch.setattr(appeal_mod, "settle", no_settle)
    client = TestClient(main.app, headers={"Authorization": "Bearer offline-demo"})
    r = _ruling(get_store())
    ok = client.post("/api/appeals", json={"ruling_id": r.id, "party": "rider", "evidence": "Receipt S$12.40"})
    assert ok.status_code == 200 and ok.json()["status"] == "checking"
    assert client.post("/api/appeals", json={"ruling_id": r.id + 999, "party": "rider", "evidence": "x"}).status_code == 404
    assert client.post("/api/appeals", json={"ruling_id": r.id, "party": "rider", "evidence": " "}).status_code == 400
    sure = _ruling(get_store(), confidence=0.97)
    assert client.post("/api/appeals", json={"ruling_id": sure.id, "party": "rider", "evidence": "x"}).status_code == 400
    st = client.get(f"/api/status/{r.id}").json()
    assert st["appeal"]["status"] == "checking" and st["final"] is None
    assert "rationale" not in json.dumps(st) and "confidence" not in json.dumps(st)
    assert client.get(f"/api/status/{sure.id}").json()["appeal_open"] is False
    assert client.get("/api/status/99999999").status_code == 404
