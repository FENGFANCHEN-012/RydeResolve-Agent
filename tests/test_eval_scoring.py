"""
Offline tests for the evaluation scoring in scripts/eval.py (no LLM, no network).
"""
import importlib.util
from pathlib import Path

import pytest

_spec = importlib.util.spec_from_file_location(
    "rr_eval", Path(__file__).resolve().parent.parent / "scripts" / "eval.py")
ev = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(ev)

SCENARIO_2 = "Dispute Resolution Guide > Scenario 2: No-Show Charge (Rider Charged But Was Present)"


def _case(**expected):
    base = {"verdict": "upheld", "refund_amount": 8.0, "requires_human_review": False,
            "must_escalate": False, "expected_dispute_type": "no_show", "expected_urgency": None,
            "expected_policy_sections": [SCENARIO_2]}
    return {"dispute_id": "NS-001", "order_id": "RYDE-DEMO-003", "filed_type": "no_show",
            "description": "", "expected": {**base, **expected}, "charge_cap": 8.0}


def _events(status="resolved", verdict="upheld", refund=8.0, refs=("Dispute Resolution Guide#2",),
            dispute_type="no_show", urgency="P1", step_error=False):
    events = [
        {"type": "run_start", "ts": 100.0},
        {"type": "retrieval", "ts": 101.0, "clauses": [
            {"source": "Dispute Resolution Guide", "section": SCENARIO_2.split(" > ")[1],
             "reference": "Dispute Resolution Guide#2"},
            {"source": "Cancellation Policy", "section": "2. Cancellation Fee Structure",
             "reference": "Cancellation Policy#2"}]},
        {"type": "llm_call", "ts": 102.0, "usage": {"prompt_tokens": 1000, "completion_tokens": 200},
         "wait_ms": 3000},
        {"type": "step_end", "ts": 103.0, "agent": "Arbitrator", "duration_ms": 2000},
    ]
    if step_error:
        events.append({"type": "step_error", "ts": 104.0, "agent": "Policy", "error": "boom", "duration_ms": 5})
    events.append({"type": "result", "ts": 110.0, "result": {
        "status": status,
        "classification": {"dispute_type": dispute_type, "urgency": urgency},
        "verdict": {"verdict": verdict, "refund_amount": refund, "policy_references": list(refs)}}})
    return events


def test_correct_run_scores_everything_ok():
    row = ev.score_run(_case(), _events())
    assert row["verdict_ok"] and row["refund_ok"] and row["escalation_ok"] and row["type_ok"]
    assert row["hit_at_3"] is True
    assert row["citations"] == 1 and row["citations_valid"] == 1
    assert row["refund_cap_ok"] is True
    assert row["duration_s"] == 10.0 and row["wait_s"] == 3.0
    assert row["prompt_tokens"] == 1000 and row["completion_tokens"] == 200
    assert row["failed"] is False


def test_wrong_verdict_and_refund():
    row = ev.score_run(_case(), _events(verdict="dismissed", refund=0.0))
    assert row["verdict_ok"] is False and row["refund_ok"] is False


def test_hallucinated_citation_is_counted_invalid():
    row = ev.score_run(_case(), _events(refs=("Dispute Resolution Guide#2", "Made Up Policy#9")))
    assert row["citations"] == 2 and row["citations_valid"] == 1


def test_escalated_case_must_escalate():
    case = _case(verdict=None, refund_amount=None, requires_human_review=True, must_escalate=True)
    assert ev.score_run(case, _events(status="escalated_to_human"))["verdict_ok"] is True
    missed = ev.score_run(case, _events(status="resolved"))
    assert missed["verdict_ok"] is False and missed["escalation_ok"] is False


def test_unneeded_escalation_is_wrong():
    row = ev.score_run(_case(), _events(status="escalated_to_human"))
    assert row["verdict_ok"] is False and row["escalation_ok"] is False


def test_p0_case_scores_escalation():
    case = _case(verdict=None, refund_amount=None, must_escalate=True, expected_urgency="P0",
                 expected_dispute_type=None)
    row = ev.score_run(case, _events(status="escalated_to_human", urgency="P0"))
    assert row["p0_escalated"] is True and row["urgency_ok"] is True and row["type_ok"] is None


def test_refund_above_charge_breaks_the_cap():
    row = ev.score_run(_case(refund_amount=None), _events(refund=50.0))
    assert row["refund_cap_ok"] is False


def test_step_error_marks_run_failed():
    assert ev.score_run(_case(), _events(step_error=True))["failed"] is True


def test_summary_targets():
    rows = [ev.score_run(_case(), _events()), ev.score_run(_case(), _events(verdict="dismissed", refund=0.0))]
    s = ev.summarise(rows)
    assert s["metrics"]["verdict_accuracy"]["value"] == 0.5
    assert s["metrics"]["verdict_accuracy"]["passed"] is False
    assert s["metrics"]["failure_rate"]["passed"] is True
    assert s["tokens"]["per_correct_verdict"] == 2400


def test_answer_keys_have_eval_fields():
    cases = ev.load_cases()
    assert len(cases) == 14  # 13 mock disputes + the organiser's DISP-002 sample
    for c in cases:
        exp = c["expected"]
        for key in ("expected_dispute_type", "expected_urgency", "expected_policy_sections", "must_escalate"):
            assert key in exp, (c["dispute_id"], key)
        assert exp["must_escalate"] == exp["requires_human_review"]
        assert exp["expected_policy_sections"]


def test_organiser_sample_uses_sidecar_answer_key():
    # DISP-002 is kept verbatim in data/Dispute_format; its key lives in data/eval_answer_keys.json
    case = next(c for c in ev.load_cases() if c["dispute_id"] == "DISP-002")
    assert case["filed_type"] == "no_show_charge"
    assert case["expected"]["verdict"] == "dismissed" and case["expected"]["refund_amount"] == 0.0
    assert case["charge_cap"] == 5.0


@pytest.mark.parametrize("dispute_id", ["SI-001"])
def test_p0_safety_case_expects_escalation(dispute_id):
    case = next(c for c in ev.load_cases() if c["dispute_id"] == dispute_id)
    assert case["expected"]["expected_urgency"] == "P0" and case["expected"]["must_escalate"] is True

def test_case_policy_citation_scores_valid_only_when_present_in_case():
    ref = "platform_policy.no_fee_if_driver_delayed_beyond_eta_min"
    case = _case()
    case["case_policy_refs"] = [ref]
    assert ev.score_run(case, _events(refs=(ref,)))["citations_valid"] == 1
    assert ev.score_run(_case(), _events(refs=(ref,)))["citations_valid"] == 0
