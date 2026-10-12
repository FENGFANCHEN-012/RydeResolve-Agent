"""Rule checks (D39): code measures a trip's time rules on the records and says whether the
rule's condition holds; it never concludes when the trip's own rules change how time is counted."""
from types import SimpleNamespace

import pytest

from src.agents.case_brief import render_case_brief
from src.agents.collector_tools import rule_checks


def ctx(trip=None, events=None, policy=None, checks=None):
    return SimpleNamespace(trip=trip or {}, app_events=events or [], platform_policy=policy or {},
                           platform_policy_checks=checks or {})


def by_rule(findings):
    return {f.value["rule"].split(".", 1)[1]: f for f in findings}


# CR-001: ETA 07:55:30 shown at assignment, rider cancelled 08:08 with no arrival -> 12.5 min late
CR001 = ctx(
    trip={"scheduled_time": "2026-09-16T07:55:30+08:00", "cancellation_time": "2026-09-16T08:08:00+08:00"},
    events=[{"timestamp": "2026-09-16T07:50:30+08:00", "event_type": "driver_assigned",
             "details": "Driver assigned. ETA 5 min (07:55:30)."}],
    policy={"no_fee_if_driver_delayed_beyond_eta_min": 10, "free_cancellation_within_min_of_match": 3,
            "free_wait_time_min": 5})


def test_late_driver_and_free_window():
    r = by_rule(rule_checks(CR001))
    late = r["no_fee_if_driver_delayed_beyond_eta_min"]
    assert late.value["measured_min"] == 12.5 and late.value["met"] is True
    assert set(late.sources) >= {"app_events[0]", "trip.cancellation_time"}
    assert r["free_cancellation_within_min_of_match"].value["met"] is False      # 17.5 min > 3


def test_rule_without_its_moment_is_not_evaluated_and_names_no_record():
    f = by_rule(rule_checks(CR001))["free_wait_time_min"]      # the driver never arrived
    assert "not evaluated" in f.statement and f.sources == [] and f.kind == "fact"


def test_eta_in_minutes_counts_from_assignment():
    c = ctx(trip={"cancellation_time": "2026-09-16T08:20:00+08:00"},
            events=[{"timestamp": "2026-09-16T08:00:00+08:00", "event_type": "driver_assigned",
                     "details": "Driver assigned. ETA 9 min."}],
            policy={"no_fee_if_driver_delayed_beyond_eta_min": 10})
    f = by_rule(rule_checks(c))["no_fee_if_driver_delayed_beyond_eta_min"]
    assert f.value["measured_min"] == 11 and f.value["met"] is True


# NS-002 family: arrival 17:59, wait threshold 8
def ns(cancel, **extra):
    return ctx(trip={"driver_arrival_time": "2026-09-21T17:59:00+08:00",
                     "driver_wait_start": "2026-09-21T17:59:00+08:00", "cancellation_time": cancel},
               policy={"no_show_threshold_min": 8, **extra})


@pytest.mark.parametrize("cancel,extra,met,word", [
    ("2026-09-21T18:06:00+08:00", {}, False, "NOT MET"),                        # NS-002-B1: 7 < 8
    ("2026-09-21T18:08:00+08:00", {}, True, "MET"),                             # 9 >= 8
    ("2026-09-21T18:07:00+08:00", {}, True, "the rules do not say"),            # exactly 8, no boundary rule
    ("2026-09-21T18:07:00+08:00", {"no_show_threshold_inclusive": False}, False, "does not count"),
    ("2026-09-21T18:07:00+08:00", {"threshold_inclusive": True}, True, "the limit counts"),
])
def test_no_show_threshold(cancel, extra, met, word):
    f = by_rule(rule_checks(ns(cancel, **extra)))["no_show_threshold_min"]
    assert f.value["met"] is met and word in f.statement


def test_time_basis_rule_blocks_the_conclusion():
    # DS-04: the trip counts from the device tap time, not the server's cancellation_time
    c = ctx(trip={"cancellation_time": "2026-10-08T09:23:25+08:00"},
            events=[{"timestamp": "2026-10-08T09:20:00+08:00", "event_type": "driver_assigned"}],
            policy={"free_cancellation_within_min_of_match": 3, "cancellation_time_basis": "device_tap_time"})
    f = by_rule(rule_checks(c))["free_cancellation_within_min_of_match"]
    assert f.value["met"] is None and "Not concluded" in f.statement and "device_tap_time" in f.statement


def test_case_check_overrides_and_reads_the_direction():
    # DS-09: free only when cancelled at least 15 min before the scheduled time; cancelled 8.8 min before
    c = ctx(trip={"scheduled_time": "2026-10-08T18:00:00+08:00", "cancellation_time": "2026-10-08T17:51:10+08:00"},
            policy={"free_before_pickup_min": 15},
            checks={"free_before_pickup_min": {"from": "cancelled", "to": "scheduled", "op": ">=",
                                               "condition": "cancelled at least {value} min before pickup"}})
    f = by_rule(rule_checks(c))["free_before_pickup_min"]
    assert f.value["measured_min"] == 8.8 and f.value["met"] is False
    assert "cancelled at least 15 min before pickup" in f.statement


def test_no_policy_no_checks():
    assert rule_checks(ctx(trip={"cancellation_time": "2026-10-08T17:51:10+08:00"})) == []


def test_brief_shows_rule_checks_and_marks_a_disputed_arrival():
    brief = {"dispute_type": "no_show", "facts": [], "conflicts": [], "gaps": [],
             "rule_checks": [{"id": "rule_check.no_show_threshold_min", "statement": "S1",
                              "sources": ["trip.driver_wait_start"], "disputed": True},
                             {"id": "rule_check.free_wait_time_min", "statement": "S2",
                              "sources": [], "disputed": False}]}
    text = render_case_brief({"case_brief": brief})
    assert "Rule checks (code measured" in text and "[rule_check.free_wait_time_min] S2" in text
    assert "Rule checks computed FROM A DISPUTED RECORD" in text


@pytest.mark.asyncio
async def test_arrival_conflict_disputes_the_wait_start(monkeypatch):
    from src.agents.case_brief import CaseBriefAgent
    from src.agents.collector_tools import Finding

    async def no_clauses(*a, **k):
        return []
    agent = CaseBriefAgent(retriever=object())
    monkeypatch.setattr(agent, "_clauses", no_clauses)
    context = {"type": "no_show", "app_events": [], "findings": [
        Finding(id="consistency.arrival_gps_far", tool="consistency_check", kind="conflict", statement="far",
                sources=["app_events[2]", "gps_trace[2]"]),
        Finding(id="rule_check.no_show_threshold_min", tool="rule_checks", kind="fact", statement="8 min",
                sources=["trip.driver_wait_start", "trip.cancellation_time"])]}
    brief = await agent.build(context)
    assert brief["rule_checks"][0]["disputed"] is True
    assert all(f["id"] != "rule_check.no_show_threshold_min" for f in brief["facts"])
