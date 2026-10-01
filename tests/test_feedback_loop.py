"""Learning feedback loop: record store, precedent lifecycle, release gate, precedent search."""
from types import SimpleNamespace

import pytest

from src.agents.arbitrator import ArbitrationAgent
from src.rag.precedents import PrecedentIndex, summarize_case
from src.store import feedback
from src.store.db import ACTIVE, PENDING, REJECTED, RETIRED, STAGED, AuditEntry, Store, case_family


@pytest.fixture
def store(tmp_path):
    return Store(f"sqlite:///{(tmp_path / 'test.db').as_posix()}")


class FakeQdrant:
    """Stands in for QdrantStore: keeps payloads, returns them all on search."""

    def __init__(self):
        self.points = {}

    def upsert(self, chunks):
        for c in chunks:
            self.points[c["id"]] = {**c["metadata"], "text": c["text"]}

    def delete(self, ids):
        for i in ids:
            self.points.pop(i, None)

    def search_points(self, query, limit=5):
        return [SimpleNamespace(payload=p, score=0.5) for p in list(self.points.values())[:limit]]


def _ruling(store, dispute_id="NS-002", status="resolved", verdict="upheld"):
    return store.record_ruling(dispute_id=dispute_id, order_id="RYDE-1", dispute_type="no_show", status=status,
                               verdict=verdict, refund_amount=8.0, confidence=0.9, rationale="r",
                               case_summary="no_show dispute. driver waited 8 min")


def test_override_creates_pending_precedent(store):
    r = _ruling(store)
    review, precedent = store.submit_review(r.id, "alice", "override", "Rider was late by her own account",
                                            final_verdict="dismissed", final_refund=0.0)
    assert precedent.status == PENDING and precedent.verdict == "dismissed" and precedent.ai_verdict == "upheld"


def test_confirm_of_a_correct_auto_ruling_is_not_a_precedent(store):
    r = _ruling(store)
    _, precedent = store.submit_review(r.id, "alice", "confirm", "Correct")
    assert precedent is None


def test_decision_on_an_escalated_case_is_a_precedent(store):
    r = _ruling(store, status="escalated_to_human", verdict=None)
    _, precedent = store.submit_review(r.id, "alice", "override", "GPS lost; refund by default",
                                       final_verdict="upheld", final_refund=5.0)
    assert precedent is not None


def test_review_needs_a_reason(store):
    r = _ruling(store)
    with pytest.raises(ValueError):
        store.submit_review(r.id, "alice", "override", "   ", final_verdict="dismissed")


def test_lifecycle_and_rollback(store):
    index = PrecedentIndex(store=FakeQdrant())
    r = _ruling(store)
    _, p = store.submit_review(r.id, "alice", "override", "late rider", final_verdict="dismissed", final_refund=0.0)
    feedback.approve(store, index, p.id, "admin")
    assert store.get_precedent(p.id).status == STAGED
    with pytest.raises(ValueError):  # cannot approve twice
        feedback.approve(store, index, p.id, "admin")
    summary = {"metrics": {"verdict_accuracy": {"value": 0.8}}, "by_set": {}}
    passed, _, moved = feedback.release_staged(store, index, summary, summary, "admin", "base", "cand")
    assert passed and moved == [p.id] and store.get_precedent(p.id).status == ACTIVE
    feedback.retire(store, index, p.id, "admin", "caused a wrong ruling")
    assert store.get_precedent(p.id).status == RETIRED and not index.store.points


def test_gate_rejects_when_safety_or_heldout_drops(store):
    base = {"metrics": {"verdict_accuracy": {"value": 0.80}, "p0_escalation_recall": {"value": 1.0}},
            "by_set": {"heldout": {"verdict_accuracy": 0.77}}}
    better_but_unsafe = {"metrics": {"verdict_accuracy": {"value": 0.90}, "p0_escalation_recall": {"value": 0.5}},
                         "by_set": {"heldout": {"verdict_accuracy": 0.85}}}
    worse_heldout = {"metrics": {"verdict_accuracy": {"value": 0.85}, "p0_escalation_recall": {"value": 1.0}},
                     "by_set": {"heldout": {"verdict_accuracy": 0.70}}}
    assert feedback.gate(base, better_but_unsafe)[0] is False
    assert feedback.gate(base, worse_heldout)[0] is False
    assert feedback.gate(base, base)[0] is True


def test_failed_gate_rejects_and_unindexes(store):
    index = PrecedentIndex(store=FakeQdrant())
    r = _ruling(store)
    _, p = store.submit_review(r.id, "alice", "override", "x", final_verdict="dismissed", final_refund=0.0)
    feedback.approve(store, index, p.id, "admin")
    base = {"metrics": {"verdict_accuracy": {"value": 0.8}}}
    cand = {"metrics": {"verdict_accuracy": {"value": 0.7}}}
    passed, reasons, _ = feedback.release_staged(store, index, base, cand, "admin", "b", "c")
    assert not passed and reasons and store.get_precedent(p.id).status == REJECTED and not index.store.points


def test_search_hides_staged_and_own_family(store, monkeypatch):
    fake = FakeQdrant()
    index = PrecedentIndex(store=fake)
    fake.upsert([{"id": "precedent-1", "text": "t", "metadata": {"precedent_id": 1, "family": "NS-002", "status": ACTIVE}},
                 {"id": "precedent-2", "text": "t", "metadata": {"precedent_id": 2, "family": "NS-001", "status": ACTIVE}},
                 {"id": "precedent-3", "text": "t", "metadata": {"precedent_id": 3, "family": "CR-002", "status": STAGED}}])
    monkeypatch.delenv("PRECEDENTS_INCLUDE_STAGED", raising=False)
    # NS-002-C1 is a variant of NS-002: its family's precedent must not answer it
    assert [h["precedent_id"] for h in index.search("q", "NS-002-C1")] == [2]
    monkeypatch.setenv("PRECEDENTS_INCLUDE_STAGED", "1")
    assert [h["precedent_id"] for h in index.search("q", "NS-002-C1")] == [2, 3]


def test_audit_chain_detects_tampering(store):
    r = _ruling(store)
    store.submit_review(r.id, "alice", "override", "late", final_verdict="dismissed", final_refund=0.0)
    assert store.verify_audit_chain() == (True, None)
    with store.session() as s:
        entry = s.get(AuditEntry, 2)
        entry.detail = {**entry.detail, "final_verdict": "upheld"}  # someone edits history
        s.commit()
    ok, bad_id = store.verify_audit_chain()
    assert not ok and bad_id == 2


def test_case_family():
    assert case_family("NS-002-C1") == "NS-002" and case_family("NS-002") == "NS-002"
    assert case_family("DISP-002") == "DISP-002"


def test_summary_uses_findings_not_arguments():
    ctx = {"type": "no_show", "reporter": "passenger", "description": "Driver never came",
           "findings": [{"kind": "gap", "statement": "Driver GPS stopped at 07:19"}]}
    text = summarize_case(ctx)
    assert "no_show dispute" in text and "[gap] Driver GPS stopped at 07:19" in text


def test_judge_prompt_shows_precedents_only_when_there_are_some():
    args = ({"dispute_id": "X"}, {}, {}, {}, [])
    assert "PRECEDENTS" not in ArbitrationAgent._build_user_prompt(*args)
    prompt = ArbitrationAgent._build_user_prompt(*args, [{"precedent_id": 7, "verdict": "dismissed"}])
    assert "PRECEDENTS" in prompt and '"precedent_id": 7' in prompt
