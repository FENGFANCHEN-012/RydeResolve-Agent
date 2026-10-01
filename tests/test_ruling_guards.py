"""Label follows the refund; fees kept on a contradicted or unmet basis go to a person (D15).
Cases from eval run 20261001-114026."""
import pytest

from src.agents.arbitrator import align_verdict_label
from src.agents.fairness import _fee_basis_problems

FEE_8 = {"id": "fee_check.charged", "kind": "fact", "value": {"fee": 8.0}}
EXCESS_370 = {"id": "fare_check.quoted_vs_charged", "kind": "fact", "value": {"difference": 3.7}}
WAITED_7 = {"id": "wait_time.waited_before_cancel", "kind": "fact", "value": {"minutes_waited": 7.0}}
WAITED_8 = {"id": "wait_time.waited_before_cancel", "kind": "fact", "value": {"minutes_waited": 8.0}}
ARRIVAL_CONFLICT = {"id": "consistency.arrival_gps_far", "kind": "conflict",
                    "statement": "driver_arrived was logged but GPS was 0.96 km away."}


def ctx(findings, type_="no_show", threshold=8, reason="rider_no_show"):
    return {"type": type_, "findings": findings, "platform_policy": {"no_show_threshold_min": threshold},
            "trip": {"cancellation_reason": reason}}


# ---- label
def test_full_refund_of_the_excess_is_upheld():                     # RD-001-P4
    out = align_verdict_label({"verdict": "partially_upheld", "refund_amount": 3.7, "rationale": "r"},
                              ctx([EXCESS_370], "route_deviation"))
    assert out["verdict"] == "upheld" and "S$3.70" in out["rationale"]


def test_part_refund_stays_partial():
    out = align_verdict_label({"verdict": "partially_upheld", "refund_amount": 2.0}, ctx([EXCESS_370]))
    assert out["verdict"] == "partially_upheld"


def test_no_disputed_amount_in_data_changes_nothing():
    out = align_verdict_label({"verdict": "partially_upheld", "refund_amount": 5.0}, ctx([]))
    assert out["verdict"] == "partially_upheld"


# ---- fee basis
def test_fee_kept_although_arrival_is_contradicted():             # NS-002-C1
    problems = _fee_basis_problems(ctx([FEE_8, WAITED_8, ARRIVAL_CONFLICT]), "dismissed", None)
    assert any("contradicts that arrival" in p for p in problems)


def test_fee_kept_although_wait_is_below_threshold():             # NS-002-B1
    problems = _fee_basis_problems(ctx([FEE_8, WAITED_7]), "dismissed", None)
    assert any("below" in p and "no_show_threshold_min" in p for p in problems)


def test_fee_kept_when_basis_is_met_is_fine():                     # NS-002 (driver waited 8, no conflict)
    assert _fee_basis_problems(ctx([FEE_8, WAITED_8]), "dismissed", None) == []


def test_fee_refunded_is_never_flagged():                          # NS-001 upheld with refund
    assert _fee_basis_problems(ctx([FEE_8, WAITED_7, ARRIVAL_CONFLICT]), "upheld", 8.0) == []


def test_other_dispute_types_are_not_checked():
    assert _fee_basis_problems(ctx([FEE_8, ARRIVAL_CONFLICT], "fare_dispute"), "dismissed", None) == []


@pytest.mark.asyncio
async def test_fairness_sends_the_contradicted_fee_to_a_person():
    from tests.test_fairness_agent import FakeLLMClient, make_context, make_decision, make_input
    from src.agents.fairness import FairnessAgent, FairnessIssueCode
    from src.agents.arbitrator import Verdict
    c = make_context(type="no_show", findings=[FEE_8, WAITED_8, ARRIVAL_CONFLICT],
                     platform_policy={"no_show_threshold_min": 8}, trip={"cancellation_reason": "rider_no_show"})
    a = await FairnessAgent(llm_client=FakeLLMClient()).assess(
        make_input(context=c, decision=make_decision(verdict=Verdict.DISMISSED, refund_amount=None)))
    assert FairnessIssueCode.FEE_BASIS_NOT_MET in {i.code for i in a.issues}
    assert a.requires_human_review is True
