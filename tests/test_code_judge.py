"""Code Judge (D38): decisive facts must be verified; a refund must be arithmetic on record figures."""
from types import SimpleNamespace

import pytest

from src.agents import code_judge
from src.agents.code_judge import check_amount, check_facts, record_numbers, review

CTX = {
    "trip": {"total_fare": 25.9, "estimated_fare": 22.8, "pickup_time": "2026-10-09T07:40:00+08:00",
             "trip_id": "RYDE-DS-011"},
    "payment": {"amount": 25.9},
    "app_events": [{"timestamp": "2026-10-09T07:53:00+08:00", "event_type": "telemetry_gap_start"},
                   {"timestamp": "2026-10-09T08:03:30+08:00", "event_type": "traffic_feed_status",
                    "details": "feed outage 07:40-08:10"}],
    "platform_policy": {"cleaning_fee_max": 40, "extra_distance_rate_per_km": 1.2},
    "findings": [
        {"id": "fare_check.quoted_vs_charged", "kind": "fact", "value": {"difference": 3.1}, "sources": ["trip"]},
        {"id": "data_gaps.data_problem_event[0]", "kind": "gap", "statement": "telemetry gap",
         "sources": ["app_events[0]"]},
        {"id": "consistency.arrival_gps_far", "kind": "conflict", "statement": "GPS 0.96 km away",
         "sources": ["app_events[1]", "gps_trace[2]"]},
    ],
}


def dec(refund=None, calc=None, facts=None):
    return SimpleNamespace(refund_amount=refund, refund_calculation=calc,
                           decisive_facts=facts if facts is not None else
                           [{"fact": "fare excess", "sources": ["trip"], "status": "verified"}])


# ---- record figures
def test_dates_times_and_ids_are_not_figures():
    nums = record_numbers(CTX)
    assert 25.9 in nums and 3.1 in nums and 40 in nums and 1.2 in nums
    assert not ({2026, 9, 53, 7, 8, 11} & nums)       # from timestamps, "07:40-08:10", RYDE-DS-011


# ---- amount
@pytest.mark.parametrize("refund,calc,ok", [
    (3.1, "3.1", True),                    # the disputed excess
    (3.1, "25.90 - 22.80", True),          # charged minus quoted
    (4.8, "4 * 1.2", False),               # 4 is not a record figure here
    (1.55, "3.10 / 2", False),             # RD-002: halving is not in the records
    (3.1, None, False),                    # no calculation
    (3.0, "25.9 - 22.8", False),           # arithmetic does not give the refund
    (5.0, "five dollars", False),          # not arithmetic
    (None, None, True),                    # nothing refunded
])
def test_refund_must_be_arithmetic_on_record_figures(refund, calc, ok):
    assert (check_amount(dec(refund, calc), CTX) == []) is ok


# ---- decisive facts
def test_no_facts_is_a_problem():
    assert check_facts(dec(facts=[]), CTX)


@pytest.mark.parametrize("status,sources,ok", [
    ("verified", ["trip"], True),
    ("unverifiable", ["app_events[1]"], False),         # DS-11 / DS-20: rests on what cannot be checked
    ("contradicted", ["gps_trace[2]"], False),
    ("verified", ["app_events[0]"], False),             # a gap finding names that record
    ("verified", ["app_events[1]"], False),             # a conflict finding names it (NS-002-C1)
    ("maybe", ["trip"], False),
])
def test_facts_must_be_verified(status, sources, ok):
    d = dec(facts=[{"fact": "x", "sources": sources, "status": status}])
    assert (check_facts(d, CTX) == []) is ok


def test_ruling_on_a_data_failure_is_not_verified():
    # Kept strict on purpose (D38): loosening it for facts that only state the failure let DS-20's
    # first draft ("attachments failed to upload" -> refund S$180) execute without a remand
    d = dec(facts=[{"fact": "Telemetry gap from 07:53 to 08:03", "sources": ["app_events[0]"],
                    "status": "verified"}])
    assert check_facts(d, CTX)


def test_conflict_questions_only_its_questioned_sources():
    # NS-001: trip record and app log agree there was no arrival; only the no-show label is in
    # question, so "driver never arrived" on those records stays verified
    ctx = {"findings": [{"id": "consistency.no_show_without_arrival", "kind": "conflict",
                         "statement": "no-show without arrival",
                         "sources": ["trip.cancellation_reason", "trip.driver_arrival_time", "app_events"],
                         "questioned": ["trip.cancellation_reason"]}]}
    never_arrived = [{"fact": "driver never arrived", "sources": ["trip.driver_arrival_time"],
                      "status": "verified"}]
    no_show = [{"fact": "rider was a no-show", "sources": ["trip.cancellation_reason"], "status": "verified"}]
    assert check_facts(dec(facts=never_arrived), ctx) == []
    assert check_facts(dec(facts=no_show), ctx)


def test_collector_marks_no_show_label_as_questioned():
    from types import SimpleNamespace as NS
    from src.agents.collector_tools import consistency_check
    ctx = NS(trip={"cancellation_reason": "rider_no_show", "driver_arrival_time": None},
             app_events=[{"event_type": "trip_cancelled", "timestamp": "2026-10-09T09:00:00+08:00"}],
             gps_trace=[], platform_policy={})
    f = {x.id: x for x in consistency_check(ctx)}["consistency.no_show_without_arrival"]
    assert f.questioned == ["trip.cancellation_reason"]


def test_review_combines_both():
    d = dec(1.55, "3.10 / 2", [{"fact": "closure", "sources": ["app_events[1]"], "status": "unverifiable"}])
    assert len(review(d, CTX)) == 2


# ---- remand: dropping the blocked record does not pass (D42, SA-08)
def pay(refund, sources, status="verified", verdict="upheld"):
    return SimpleNamespace(verdict=verdict, refund_amount=refund, refund_calculation=str(refund),
                           decisive_facts=[{"fact": "driver never arrived", "sources": sources, "status": status}])


@pytest.mark.parametrize("revised,ok", [
    (pay(8.0, ["gps_trace[8]"]), False),                          # SA-08: same payout, blocked record dropped
    (pay(0, ["gps_trace[8]"], verdict="dismissed"), True),        # ruling changed: no money rests on it
    (pay(5.0, ["gps_trace[8]"]), True),                           # amount changed: left to check_amount
    (pay(8.0, ["gps_trace[8]", "app_events[0]"], "unverifiable"), True),  # kept and marked: check_facts sends it on
])
def test_remand_cannot_just_drop_the_blocked_record(revised, ok):
    first = pay(8.0, ["gps_trace[8]", "app_events[0]"])          # app_events[0] is named by a gap finding
    assert check_facts(first, CTX)
    assert (code_judge.check_remand(first, revised, CTX) == []) is ok


def test_remand_rule_ignores_drafts_blocked_for_other_reasons():
    # NS-001 / DR-002 replays: first draft blocked for a status, not a questioned record; a revised
    # draft with the same payout is the Judge correcting itself and passes this rule
    first = pay(8.0, ["trip"], "unverifiable")
    assert code_judge.check_remand(first, pay(8.0, ["trip"]), CTX) == []


# ---- workflow: a failed check goes back to the Judge once, then to a person
class SeqArbitrator:
    """Returns the given decisions in turn and records whether each call carried a code review."""
    def __init__(self, decisions):
        self.decisions, self.reviews = list(decisions), []

    async def arbitrate(self, context, passenger_analysis, driver_analysis, policy_evaluation,
                        debate_history, code_review=None, **kw):
        self.reviews.append(code_review)
        return self.decisions.pop(0)

    def _build_valid_refs(self, *a, **k):
        return set()


def ruling(status):
    from src.agents.arbitrator import Decision, Verdict
    return Decision(verdict=Verdict.DISMISSED, confidence=0.9, rationale="r",
                    decisive_facts=[{"fact": "the driver waited", "sources": ["trip"], "status": status}])


@pytest.mark.asyncio
@pytest.mark.parametrize("statuses,judge_calls,executed", [
    (["verified"], 1, True),                         # clean: no second call, executes
    (["unverifiable", "verified"], 2, True),         # fixed after the code check
    (["unverifiable", "unverifiable"], 2, False),    # still unverifiable: a person decides
])
async def test_workflow_code_judge(monkeypatch, statuses, judge_calls, executed):
    monkeypatch.setattr(code_judge, "CODE_JUDGE", True)
    from tests.test_workflow_graph import StubExecutor, build_graph, initial_state
    judge, executor = SeqArbitrator([ruling(s) for s in statuses]), StubExecutor()
    final = await build_graph(arbitrator=judge, executor=executor).ainvoke(initial_state())
    assert len(judge.reviews) == judge_calls
    if judge_calls == 2:
        assert judge.reviews[0] is None and "CODE CHECK" in judge.reviews[1]
    assert (executor.calls == 1) is executed
