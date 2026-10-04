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


# ---- label from the asks (run 20261002-105854)
from src.agents.arbitrator import label_from_asks
from src.agents.fairness import _location_evidence_gaps


def asks(*outcomes):
    return [{"ask": f"ask {i}", "outcome": o} for i, o in enumerate(outcomes)]


def test_one_ask_partly_granted_is_partial():                       # SQ-002: S$4.20 of S$22.60
    out = label_from_asks({"verdict": "upheld", "asks": asks("partly", "granted"), "rationale": ""})
    assert out["verdict"] == "partially_upheld" and "[Label:" in out["rationale"]


def test_already_resolved_counts_as_satisfied():                    # CR-003 (user decision 2026-10-02)
    out = label_from_asks({"verdict": "partially_upheld", "asks": asks("granted", "already_resolved")})
    assert out["verdict"] == "upheld"


def test_one_ask_denied_of_two_is_partial():
    out = label_from_asks({"verdict": "upheld", "asks": asks("granted", "denied")})
    assert out["verdict"] == "partially_upheld"


def test_all_denied_is_dismissed():
    assert label_from_asks({"verdict": "partially_upheld", "asks": asks("denied")})["verdict"] == "dismissed"


def test_missing_or_malformed_asks_keep_the_judge_label():
    assert label_from_asks({"verdict": "upheld"})["verdict"] == "upheld"
    assert label_from_asks({"verdict": "upheld", "asks": [{"ask": "x", "outcome": "maybe"}]})["verdict"] == "upheld"


def test_full_refund_rule_skips_two_ask_filings():                  # SQ-002: refund = detour excess
    parsed = {"verdict": "partially_upheld", "refund_amount": 3.7, "asks": asks("partly", "granted")}
    assert align_verdict_label(parsed, ctx([EXCESS_370], "service_quality"))["verdict"] == "partially_upheld"


def test_full_refund_rule_defers_to_an_asks_list():                 # SQ-002, run 20261004-083956
    parsed = {"verdict": "partially_upheld", "refund_amount": 3.7, "asks": asks("partly"), "rationale": ""}
    assert align_verdict_label(parsed, ctx([EXCESS_370], "route_deviation"))["verdict"] == "partially_upheld"


# ---- GPS gap on fare disputes: only a metered fare depends on the route (FD-003)
GPS_LOST = {"id": "data_gaps.gps_signal_lost", "kind": "gap", "statement": "GPS lost for 12.5 min."}


def fare_ctx(findings, basis=None, booking=""):
    return {"type": "fare_dispute", "findings": findings, "platform_policy": {"fare_basis": basis} if basis else {},
            "app_events": [{"event_type": "booking_confirmed", "details": booking}]}


def test_metered_fare_with_gps_gap_is_blocked():
    assert _location_evidence_gaps(fare_ctx([GPS_LOST], basis="metered_for_rydetaxi"))
    assert _location_evidence_gaps(fare_ctx([GPS_LOST], booking="RydeTAXI trip (metered fare, estimate S$19.20)."))


def test_upfront_fare_with_gps_gap_is_not_blocked():                # the quote fixes the fare
    assert _location_evidence_gaps(fare_ctx([GPS_LOST], booking="Upfront quoted fare S$12.00.")) == []


def test_metered_fare_without_gap_is_not_blocked():
    assert _location_evidence_gaps(fare_ctx([], basis="metered_for_rydetaxi")) == []


# ---- D17: catch payouts the platform data contradicts (run 20261002-211912)
from src.agents.fairness import _refund_basis_problems

NO_ARRIVAL_12 = {"id": "wait_time.no_arrival", "kind": "fact", "value": {"minutes_after_scheduled": 12.5}}
NO_ARRIVAL_9 = {"id": "wait_time.no_arrival", "kind": "fact", "value": {"minutes_after_scheduled": 9.0}}
FEE_4 = {"id": "fee_check.charged", "kind": "fact", "value": {"fee": 4.0}}
EXCESS_420 = {"id": "fare_check.quoted_vs_charged", "kind": "fact", "value": {"difference": 4.2}}


def cancel_ctx(findings, limit=10):
    return {"type": "cancellation_refund", "findings": findings,
            "platform_policy": {"no_fee_if_driver_delayed_beyond_eta_min": limit},
            "trip": {"cancellation_reason": "rider_cancelled_after_assignment"}}


def test_fee_kept_although_driver_late_beyond_waiver():               # CR-001
    problems = _fee_basis_problems(cancel_ctx([FEE_4, NO_ARRIVAL_12]), "dismissed", None)
    assert any("no_fee_if_driver_delayed_beyond_eta_min" in p for p in problems)


def test_fee_kept_when_driver_within_waiver_limit_is_fine():
    assert _fee_basis_problems(cancel_ctx([FEE_4, NO_ARRIVAL_9]), "dismissed", None) == []


def test_fee_refunded_after_late_driver_is_fine():
    assert _fee_basis_problems(cancel_ctx([FEE_4, NO_ARRIVAL_12]), "upheld", 4.0) == []


def test_refund_beyond_disputed_amount_is_flagged():                  # SQ-002: S$22.60 vs S$4.20
    assert _refund_basis_problems({"findings": [EXCESS_420]}, 22.6)


def test_refund_of_the_disputed_amount_is_fine():
    assert _refund_basis_problems({"findings": [EXCESS_420]}, 4.2) == []


def test_refund_without_a_computed_disputed_amount_is_not_checked():  # e.g. a damage claim
    assert _refund_basis_problems({"findings": []}, 200.0) == []
    assert _refund_basis_problems({"type": "driver_rights", "findings": []}, 200.0) == []


def test_discretionary_service_quality_refund_goes_to_a_person():    # SQ-001: S$27.40, no overcharge
    assert _refund_basis_problems({"type": "service_quality", "findings": []}, 27.4)


def test_service_quality_refund_of_an_overcharge_is_fine():          # SQ-002: S$4.20 detour excess
    assert _refund_basis_problems({"type": "service_quality", "findings": [EXCESS_420]}, 4.2) == []


def test_service_quality_with_no_refund_is_fine():                    # warning only
    assert _refund_basis_problems({"type": "service_quality", "findings": []}, 0) == []
