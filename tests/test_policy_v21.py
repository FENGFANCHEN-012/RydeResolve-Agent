"""D50: the organisers' sample format and Ryde Dispute Resolution Policy v2.1."""
import asyncio
import json
from types import SimpleNamespace

import pytest

from src.agents import policy_gates
from src.agents.collector import CollectorAgent
from src.agents.collector_tools import contact_obligation, route_vs_recommended, surge_check, traffic_check
from src.core import governing_policy
from src.integrations.ryde_api import strip_answer_keys

DIR = "data/Dispute_format/"
DISP_001 = DIR + "RydeResolve Route Deviation Dataset — DISP-001.md"
DISP_002 = DIR + "RydeResolve Sample Dataset — DISP-002 No-Show Charge Dispute (SG).md"
DISP_003 = DIR + "RydeResolve Fare Dispute Dataset — DISP-003.md"


def collect(path):
    return asyncio.run(CollectorAgent().collect_from_dataset(path))


def by_id(ctx, prefix):
    return [f for f in ctx.findings if f.id.startswith(prefix)]


# ---- the sample format: records kept, analysis removed
def test_analysis_and_answers_never_reach_the_agents():
    for path in (DISP_001, DISP_002, DISP_003):
        dump = json.dumps(collect(path).model_dump(), default=str)
        for word in ("expected_ruling", "recommended_ruling", "evidence_summary", "reroute_justified",
                     "route_notification_sent", "ruling_rationale", "reasonable alternative", "root_cause",
                     "\"supports\""):
            assert word not in dump, (path, word)


def test_strip_keeps_records_and_drops_reasoning():
    data = {"trip_data": {"trip_id": "T"}, "case_metadata": {"x": 1}, "recommended_ruling": {},
            "fare_breakdown": {"excess_distance_fare": 3.44, "notes": "supporting that ...", "comparison": {}},
            "optimal_route": {"estimated_distance_km": 20.5, "notes": "the driver instead took ..."},
            "traffic_conditions": [{"road": "PIE", "severity": "high", "description": "a reasonable alternative"}]}
    out = strip_answer_keys(data)
    assert set(out) == {"trip_data", "fare_breakdown", "optimal_route", "traffic_conditions"}
    assert out["fare_breakdown"] == {"excess_distance_fare": 3.44}
    assert out["optimal_route"] == {"estimated_distance_km": 20.5}
    assert out["traffic_conditions"] == [{"road": "PIE", "severity": "high"}]


def test_sample_records_are_folded_into_the_trip_with_aliases():
    t = collect(DISP_001).trip
    assert t["pickup_time"] == t["start_time"] and t["total_fare"] == 35.0
    assert t["recommended_route"]["estimated_distance_km"] == 20.5 and len(t["traffic_incidents"]) == 3
    t = collect(DISP_003).trip
    assert t["estimated_fare"] == 12.0 and t["surge_pricing_log"]["rider_notified"] is False


# ---- record tools on the samples
def test_surge_check_on_disp_003():
    [f] = by_id(collect(DISP_003), "surge_check")
    assert f.value["solely_surge"] is True and f.value["from_surge"] == 4.5 and f.value["rider_notified"] is False
    assert "s3.3" in f.statement and "MET" in f.statement


def test_route_and_traffic_on_disp_001():
    ctx = collect(DISP_001)
    [r] = by_id(ctx, "route_vs_recommended")
    assert r.value["excess_km"] == 4.3 and r.value["beyond_tolerance"] and r.value["excess_distance_fare"] == 3.44
    t = {f.value["incident_type"]: f.value for f in by_id(ctx, "traffic_check")}
    assert t["vehicle_fire"] == {"incident_type": "vehicle_fire", "severity": "high", "active_during_trip": True,
                                 "on_recommended_route": True}
    assert t["traffic_flow"]["on_recommended_route"] is False


def test_contact_obligation_on_disp_002():
    [f] = by_id(collect(DISP_002), "contact_obligation")
    assert f.value == {"messages": 4, "calls": 1, "met": True}


def ctx(**trip):
    return SimpleNamespace(trip=trip, chat_log=[], app_events=[])


def test_tools_stay_quiet_without_their_records():
    for tool in (surge_check, route_vs_recommended, traffic_check, contact_obligation):
        assert tool(ctx(total_fare=10)) == []


def test_contact_obligation_needs_a_message_and_a_call_before_the_cancel():
    c = SimpleNamespace(trip={"cancellation_time": "2026-10-01T10:10:00+08:00", "cancellation_reason": "rider_no_show"},
                        chat_log=[{"timestamp": "2026-10-01T10:05:00+08:00", "sender": "driver", "message_type": "message"},
                                  {"timestamp": "2026-10-01T10:11:00+08:00", "sender": "driver", "message_type": "call"}],
                        app_events=[])
    [f] = contact_obligation(c)
    assert f.value == {"messages": 1, "calls": 0, "met": False} and "NOT MET" in f.statement


def test_route_within_tolerance():
    [f] = route_vs_recommended(ctx(actual_distance_km=10.8, recommended_route={"estimated_distance_km": 10.0}))
    assert f.value["beyond_tolerance"] is False and "within" in f.statement


# ---- governing policy sections
def test_policy_parses_every_section():
    s = governing_policy.sections()
    assert {"1.3", "2.3", "3.3", "4.4", "5.2", "6.1", "6.2", "6.3", "7.1", "7.2", "7.3"} <= set(s)
    assert "Partial refund of excess distance fare" in s["1.3"]["text"]


@pytest.mark.parametrize("trip,dtype,desc,urgency,must,must_not", [
    ({}, "route_deviation", "", None, {"1.3", "6.1", "7.1"}, {"2.3", "4.4", "5.2"}),
    ({"cancellation_time": "x"}, "no_show", "", None, {"2.3", "7.3"}, {"1.3"}),
    ({"surge_pricing_log": {}}, "fare_dispute", "", None, {"3.3", "7.2"}, {"4.4"}),
    ({"cleaning_fee": 40}, "fare_dispute", "", None, {"4.4"}, set()),
    ({}, "service_quality", "I felt unsafe, he was reckless", None, {"5.2"}, set()),
    ({}, "service_quality", "rude", "P0", {"5.1", "5.2"}, set()),
])
def test_sections_follow_the_case(trip, dtype, desc, urgency, must, must_not):
    got = set(governing_policy.applicable({"trip": trip, "description": desc}, dtype, urgency))
    assert must <= got and not (must_not & got)


# ---- routing gates
def dec(conf=0.9, refund=0.0, human=False):
    return SimpleNamespace(confidence=conf, refund_amount=refund, human_review_needed=human)


def gctx(**over):
    base = {"type": "fare_dispute", "reporter": "passenger", "description": "", "trip": {},
            "rider_profile": {"fraud_flags": 0}, "driver_profile": {"fraud_flags": 0}, "findings": []}
    return {**base, **over}


def fare(diff):
    return [{"id": "fare_check.quoted_vs_charged", "kind": "fact", "value": {"difference": diff}}]


@pytest.mark.parametrize("decision,context,section", [
    (dec(), gctx(findings=fare(60)), "s6.1"),                               # above S$50
    (dec(conf=0.7), gctx(findings=fare(20)), "s6.1"),                       # S$10-50, low confidence
    (dec(conf=0.9), gctx(rider_profile={"fraud_flags": 1}), "s6.3"),        # fraud flag, < 0.95
    (dec(), gctx(trip={"cleaning_fee": 40}), "s4.4"),                       # rider contests a cleaning fee
    (dec(), gctx(safety_alerts=["threat"]), "s5.2"),                        # threat in the chat
    (dec(), gctx(), None),                                                  # small, clean, confident
    (dec(conf=0.85), gctx(findings=fare(20)), None),                        # S$10-50 at 0.85
    (dec(conf=0.5), gctx(findings=fare(4.5)), None),                        # under S$10: final
    (dec(conf=0.9), gctx(type="no_show", rider_profile={"fraud_flags": 1}), None),  # s6.2: no-show final
    (dec(conf=0.99), gctx(rider_profile={"fraud_flags": 1}), None),
    (dec(), gctx(reporter="driver", trip={"cleaning_fee_claimed": 40}), None),      # driver's claim <= S$50
    (dec(human=True), gctx(findings=fare(80)), None),                       # already with a person
])
def test_policy_gates(decision, context, section):
    reasons = policy_gates.check(decision, context)
    assert (section is None and reasons == []) or any(section in r for r in reasons), reasons


def test_p0_urgency_is_a_safety_case():
    assert any("s5.2" in r for r in policy_gates.check(dec(), gctx(), urgency="P0"))


def test_a_driver_claim_above_50_goes_to_a_person():
    assert any("s6.1" in r for r in policy_gates.check(dec(), gctx(reporter="driver", trip={"cleaning_fee_claimed": 80})))


@pytest.mark.parametrize("desc,prop", [
    ("The driver sent me messages and cancelled", False),   # "message" is not "mess"
    ("He left a mess on the seat", True),
    ("Charged a cleaning fee for a spill", True),
    ("I have a clean record and was on time", False),
])
def test_property_case_words(desc, prop):
    assert governing_policy.is_property_case({"trip": {}, "description": desc}) is prop


@pytest.mark.parametrize("reporter,claimed,refund,flagged", [
    ("driver", 40.0, 40.0, False),     # V2-07: paying the recorded claim is not discretion
    ("driver", 40.0, 60.0, True),      # more than the claim: still a person's call
    ("passenger", 0, 25.0, True),      # a rider's service complaint with no amount on record
])
def test_driver_claim_on_record_is_not_discretion(reporter, claimed, refund, flagged):
    from src.agents.fairness import _refund_basis_problems
    context = {"type": "service_quality", "reporter": reporter, "findings": [],
               "trip": {"cleaning_fee_claimed": claimed} if claimed else {}}
    assert bool(_refund_basis_problems(context, refund)) is flagged


@pytest.mark.parametrize("dtype,refund,ok", [
    ("route_deviation", 6.50, False),   # DISP-001 run 20261014-201340: tolls and time refunded too
    ("route_deviation", 3.44, True),
    ("fare_dispute", 6.50, True),       # not a route ruling: other checks apply
])
def test_route_refund_is_capped_at_the_excess_distance_fare(dtype, refund, ok):
    from src.agents.code_judge import check_route_refund
    ctx = {"type": dtype, "trip": {"fare_breakdown": {"excess_distance_fare": 3.44}}}
    assert (check_route_refund(SimpleNamespace(refund_amount=refund), ctx) == []) is ok


def test_section_6_2_carries_the_route_note():
    [c] = [c for c in governing_policy.clauses_for({"trip": {}, "description": ""}, "route_deviation")
           if c["chunk_index"] == "6.2"]
    assert "RydeResolve note" in c["clause"] and "DISP-001" in c["clause"]


def test_a_repair_claim_above_50_goes_to_a_person():
    # OF-27: the claim is recorded as repair_fee_claimed
    reasons = policy_gates.check(dec(), gctx(reporter="driver", trip={"repair_fee_claimed": 245.0}))
    assert any("s6.1" in r for r in reasons)


@pytest.mark.parametrize("text,p0", [
    ("I was in the hospital lobby with my phone on silent and missed the driver.", False),   # OF-15
    ("I was dropped at Mount Elizabeth Hospital and charged twice.", False),
    ("The crash left me hurt and I was taken to hospital.", True),
    ("My son was hospitalised after the driver braked hard.", True),
])
def test_hospital_as_a_place_is_not_a_safety_word(text, p0):
    from src.agents.classifier import _has_p0_keywords
    from src.agents.safety import _IMMINENT_PATTERNS
    import re
    assert _has_p0_keywords(text)[0] is p0
    if not p0:
        assert not any(re.search(p, text.lower()) for p in _IMMINENT_PATTERNS)


@pytest.mark.parametrize("desc,events,flag", [
    ("The driver was weaving between lanes and tailgating.", [], True),           # OF-16
    ("Fare was higher than quoted.", [{"event_type": "speeding_alert"}], True),
    ("Fare was higher than quoted.", [{"event_type": "trip_completed"}], False),
])
def test_safety_indicators_flag_any_dispute(desc, events, flag):
    reasons = policy_gates.check(dec(), gctx(description=desc, app_events=events))
    assert any("s5.2" in r for r in reasons) is flag


def test_rejecting_a_drivers_claim_on_a_doubted_photo_is_allowed_paying_is_not():
    from src.agents import code_judge
    ctx = {"reporter": "driver", "trip": {"cleaning_fee_claimed": 28.0}, "description": "",
           "findings": [{"id": "photo_checks.late[0]", "kind": "conflict", "statement": "26 h late",
                         "sources": ["evidence[0]"], "questioned": ["evidence[0]"]}]}
    fact = [{"fact": "photo taken 26 h after drop-off", "sources": ["evidence[0]"], "status": "contradicted"}]
    reject = SimpleNamespace(verdict="dismissed", refund_amount=0, human_review_needed=False, decisive_facts=fact)
    pay = SimpleNamespace(verdict="upheld", refund_amount=28.0, human_review_needed=False, decisive_facts=fact)
    assert code_judge.check_photos(reject, ctx) == [] and code_judge.check_facts(reject, ctx) == []
    assert code_judge.check_photos(pay, ctx) and code_judge.check_facts(pay, ctx)


def test_rejection_fact_may_cite_the_drop_off_it_is_measured_against():
    # OF-17 run 20261015-144231: facts cited evidence[0] together with trip.dropoff_time / location
    from src.agents import code_judge
    ctx = {"reporter": "driver", "trip": {"cleaning_fee_claimed": 28.0}, "description": "",
           "findings": [{"id": "photo_checks.late[0]", "kind": "conflict", "statement": "26 h late",
                         "sources": ["evidence[0]"], "questioned": ["evidence[0]"]}]}
    facts = [{"fact": "photo 1565 min after drop-off", "sources": ["evidence[0]", "trip.dropoff_time"],
              "status": "contradicted"},
             {"fact": "claim S$28", "sources": ["trip.cleaning_fee_claimed"], "status": "verified"}]
    reject = SimpleNamespace(verdict="dismissed", refund_amount=None, human_review_needed=False, decisive_facts=facts)
    assert code_judge.check_facts(reject, ctx) == []
    other = [{"fact": "the driver arrived", "sources": ["trip.dropoff_time"], "status": "contradicted"}]
    assert code_judge.check_facts(SimpleNamespace(verdict="dismissed", refund_amount=0, decisive_facts=other), ctx)
