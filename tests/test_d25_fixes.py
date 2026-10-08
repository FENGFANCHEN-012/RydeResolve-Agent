"""D25: Judge money check + issue rulings with one remand, route timing fact, research gated by triage."""
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from src.agents import collector_tools
from src.agents.arbitrator import ArbitrationAgent, ruling_problems
from src.agents.collector import DisputeContext, DisputeType
from src.core.debate import DebateEngine
from src.core.moves import issue_summary, render_issue_summary
from src.core.triage import triage


# ---------------------------------------------------------------- route timing

def route_ctx(chat_time: str, alert_time: str = "2026-10-02T23:41:00+08:00") -> DisputeContext:
    return DisputeContext(
        dispute_id="T", type=DisputeType.ROUTE_DEVIATION, reporter="passenger", order_id="O", description="x",
        chat_log=[{"timestamp": chat_time, "sender": "driver", "message": "PIE got jam, I go via SLE ok?"}],
        app_events=[{"timestamp": alert_time, "event_type": "traffic_incident_alert", "details": "PIE closed"},
                    {"timestamp": "2026-10-02T23:58:00+08:00", "event_type": "route_recalculated"}])


def test_route_timing_flags_a_detour_raised_before_the_alert():
    [f] = collector_tools.route_timing(route_ctx("2026-10-02T23:36:50+08:00"))
    assert f.id == "route_timing.vs_incident_alert" and f.kind == "fact"
    assert "BEFORE the alert" in f.statement and "23:36" in f.statement
    assert f.value["driver_message_minutes_from_alert"] < 0
    assert f.sources == ["app_events[0]", "chat_log[0]", "app_events[1]"]


def test_route_timing_after_the_alert_and_without_an_alert():
    [f] = collector_tools.route_timing(route_ctx("2026-10-02T23:42:00+08:00"))
    assert "1.0 min after the alert" in f.statement and "BEFORE" not in f.statement
    no_alert = route_ctx("2026-10-02T23:42:00+08:00")
    no_alert.app_events = no_alert.app_events[1:]
    assert collector_tools.route_timing(no_alert) == []
    assert "route_timing" in collector_tools.STANDARD_TOOLS


# ---------------------------------------------------------------- triage gates research

def test_research_only_when_complex_or_dangerous():
    simple = DisputeContext(dispute_id="T", type=DisputeType.NO_SHOW, reporter="driver", order_id="O",
                            description="x", case_brief={"conflicts": [], "gaps": []})
    assert triage(simple, SimpleNamespace(urgency="P2"), {"level": "low"})["advocate_research"] is False
    assert triage(simple, None, {"level": "medium"})["advocate_research"] is True
    assert triage(simple, None, {"level": "low", "safety_alerts": ["x"]})["advocate_research"] is True


@pytest.mark.asyncio
async def test_debate_skips_research_when_told(monkeypatch):
    calls = []

    async def fake_research(side, context, *args, **kwargs):
        calls.append(side)
        return context, {"added_evidence": []}

    monkeypatch.setattr("src.core.debate.research_turn", fake_research)
    monkeypatch.setattr("src.core.debate.ADVOCATE_RESEARCH", True)
    engine = object.__new__(DebateEngine)
    engine.max_rounds = 1
    engine.passenger_agent = SimpleNamespace(analyze=AsyncMock(return_value={"reasoning": "p"}),
                                             rebut=AsyncMock(return_value="p rebut"))
    engine.driver_agent = SimpleNamespace(analyze=AsyncMock(return_value={"reasoning": "d"}),
                                          rebut=AsyncMock(return_value="d rebut"))
    engine.policy_agent = SimpleNamespace(evaluate_compliance=AsyncMock(return_value={"reasoning": "ok"}),
                                          _get_retriever=lambda: None)
    ctx = DisputeContext(dispute_id="T", type=DisputeType.NO_SHOW, reporter="driver", order_id="O", description="x")
    history, _ = await engine.debate_with_context(ctx, research=False)
    assert calls == [] and len(history) == 5
    await engine.debate_with_context(ctx, research=True)
    assert calls[:2] == ["passenger", "driver"]


# ---------------------------------------------------------------- issues are numbered

def turn(tid, speaker, *moves):
    return {"id": tid, "speaker": speaker, "round": 1, "moves": list(moves)}


HISTORY = [
    turn("D4", "passenger", {"type": "challenge", "target": "D2", "text": "detour began before the alert",
                             "cites": ["app_events[2]"]}),
    turn("D5", "driver", {"type": "challenge", "target": "D4", "text": "the stop was the rider's",
                          "cites": ["chat_log[2]"]}),
]


def test_contested_issues_get_ids_the_judge_must_use():
    s = issue_summary(HISTORY)
    assert [c["id"] for c in s["contested"]] == ["I1", "I2"]
    text = render_issue_summary(s)
    assert "[I1] passenger challenged D2 [D4]" in text and "issue_rulings" in text


# ---------------------------------------------------------------- ruling checks

def test_charge_correct_with_a_refund_is_a_problem():
    [p] = ruling_problems({"fare_finding": "charge_correct", "refund_amount": 3.1}, [])
    assert "charge_correct" in p and "S$3.10" in p
    assert ruling_problems({"fare_finding": "charge_correct", "refund_amount": 0}, []) == []
    assert ruling_problems({"fare_finding": "overcharged", "refund_amount": None}, [])
    assert ruling_problems({"fare_finding": "overcharged", "refund_amount": 12.5}, []) == []
    assert ruling_problems({"fare_finding": "maybe"}, [])


def test_missing_issue_rulings_are_a_problem():
    parsed = {"issue_rulings": [{"issue": "I1", "ruling": "records support the rider"}]}
    [p] = ruling_problems(parsed, ["I1", "I2"])
    assert "I2" in p and "I1" not in p
    assert ruling_problems({"issue_rulings": [{"issue": "[I1]"}, {"issue": "I2"}]}, ["I1", "I2"]) == []
    # Older replies without the new fields are not checked
    assert ruling_problems({"refund_amount": 5}, []) == []


class SequenceLLM:
    def __init__(self, *replies):
        self.replies = list(replies)
        self.calls = []

    async def chat_json(self, messages, temperature=None):
        self.calls.append(messages)
        return self.replies.pop(0)


def ruling(**over):
    base = {"asks": [{"ask": "refund", "outcome": "denied"}], "verdict": "dismissed", "confidence": 0.9,
            "refund_amount": 0, "compensation": None, "driver_penalty": None, "rationale": "fare owed",
            "policy_references": [], "escalation_recommended": False, "human_review_needed": False,
            "fare_finding": "charge_correct", "issue_rulings": []}
    base.update(over)
    return json.dumps(base)


INPUTS = dict(context={"dispute_id": "D", "type": "route_deviation"}, passenger_analysis={},
              driver_analysis={}, policy_evaluation={}, debate_history=[])


@pytest.mark.asyncio
async def test_a_contradictory_ruling_is_remanded_once_and_fixed():
    bad = ruling(asks=[{"ask": "refund", "outcome": "partly"}], verdict="partially_upheld", refund_amount=3.1)
    llm = SequenceLLM(bad, ruling())
    decision = await ArbitrationAgent(llm_client=llm).arbitrate(**INPUTS)
    assert len(llm.calls) == 2 and "Your ruling has these problems" in llm.calls[1][-1]["content"]
    assert decision.refund_amount == 0 and decision.verdict.value == "dismissed"
    assert decision.remanded_for and decision.fare_finding == "charge_correct"
    assert not decision.human_review_needed


@pytest.mark.asyncio
async def test_a_ruling_still_wrong_after_remand_goes_to_a_person():
    bad = ruling(asks=[{"ask": "refund", "outcome": "partly"}], verdict="partially_upheld", refund_amount=3.1)
    llm = SequenceLLM(bad, bad)
    decision = await ArbitrationAgent(llm_client=llm).arbitrate(**INPUTS)
    assert len(llm.calls) == 2 and decision.human_review_needed and "[CHECK:" in decision.rationale


@pytest.mark.asyncio
async def test_open_issues_need_rulings():
    inputs = {**INPUTS, "debate_history": HISTORY}
    good = ruling(issue_rulings=[{"issue": "I1", "ruling": "x"}, {"issue": "I2", "ruling": "y"}])
    llm = SequenceLLM(ruling(), good)
    decision = await ArbitrationAgent(llm_client=llm).arbitrate(**inputs)
    assert len(llm.calls) == 2 and [r["issue"] for r in decision.issue_rulings] == ["I1", "I2"]
    # A clean first ruling costs no second call
    llm = SequenceLLM(good)
    await ArbitrationAgent(llm_client=llm).arbitrate(**inputs)
    assert len(llm.calls) == 1


# ---------------------------------------------------------------- GPS gap length

from src.agents.fairness import _location_evidence_gaps  # noqa: E402


def gap_ctx(lost: str, restored: str | None) -> DisputeContext:
    events = [{"timestamp": lost, "event_type": "gps_signal_lost"}]
    if restored:
        events.append({"timestamp": restored, "event_type": "gps_signal_restored"})
    return DisputeContext(dispute_id="T", type=DisputeType.ROUTE_DEVIATION, reporter="passenger", order_id="O",
                          description="x", app_events=events,
                          trip={"pickup_time": "2026-10-02T23:31:00+08:00", "dropoff_time": "2026-10-03T00:20:00+08:00"})


def test_restored_gps_gap_states_its_length():
    [f] = collector_tools.data_gaps(gap_ctx("2026-10-02T23:44:00+08:00", "2026-10-02T23:50:00+08:00"))
    assert f.value["minutes"] == 6.0 and f.value["share_of_trip"] == 0.12
    assert "until 23:50 (6.0 min of a 49 min trip)" in f.statement
    [f] = collector_tools.data_gaps(gap_ctx("2026-10-02T23:44:00+08:00", None))
    assert "restored_at" not in f.value and "after that point" in f.statement


def fairness_ctx(ctx):
    return {"type": "route_deviation", "findings": [f.model_dump() for f in collector_tools.data_gaps(ctx)]}


def test_short_restored_gap_is_not_decisive_but_a_long_or_open_one_is():
    short = fairness_ctx(gap_ctx("2026-10-02T23:44:00+08:00", "2026-10-02T23:50:00+08:00"))
    assert _location_evidence_gaps(short) == [] and _location_evidence_gaps(short, short=True)
    long = fairness_ctx(gap_ctx("2026-10-02T23:44:00+08:00", "2026-10-03T00:00:00+08:00"))  # 16 of 49 min
    assert _location_evidence_gaps(long) and _location_evidence_gaps(long, short=True) == []
    assert _location_evidence_gaps(fairness_ctx(gap_ctx("2026-10-02T23:44:00+08:00", None)))


# ---------------------------------------------------------------- who a rule binds

def test_brief_says_who_a_rule_binds():
    from src.agents.case_brief import render_case_brief
    brief = {"dispute_type": "route_deviation", "case_rules": {"platform_policy.stops_must_be_added_in_app": True},
             "rule_binds": {"platform_policy.stops_must_be_added_in_app": "rider"}}
    text = render_case_brief({"case_brief": brief})
    assert "stops_must_be_added_in_app = True (binds: rider)" in text
    assert "do not assume it binds the driver" in text
