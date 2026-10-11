"""D32: the side a draft ruling goes against may object once; code checks the objection."""
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from src.agents.arbitrator import ArbitrationAgent, Decision, Verdict
from src.agents.objection import ObjectionAgent, check, objecting_sides, record_exists

CTX = {
    "platform_policy": {"no_show_threshold_min": 8},
    "app_events": [{"event_type": "driver_arrived"}, {"event_type": "trip_cancelled"}],
    "chat_log": [{"sender": "rider", "message": "where are you?"}],
    "findings": [{"id": "wait_time.waited_before_cancel", "kind": "fact", "value": {"minutes_waited": 7}}],
}
RULES = {"platform_policy.no_show_threshold_min"}
GOOD = {"objection": True, "claim": "The driver waited 7 min, below the 8-min threshold.",
        "rule": "platform_policy.no_show_threshold_min", "record": "wait_time.waited_before_cancel"}


def decision(verdict="dismissed", review=False):
    return Decision(verdict=Verdict(verdict), confidence=0.9, rationale="r", human_review_needed=review)


def test_the_side_the_draft_goes_against_may_object():
    assert objecting_sides(decision("dismissed"), "passenger") == ["passenger"]
    assert objecting_sides(decision("upheld"), "passenger") == ["driver"]
    assert objecting_sides(decision("partially_upheld"), "passenger") == ["passenger", "driver"]
    assert objecting_sides(decision("dismissed"), "driver") == ["driver"]


def test_no_objection_when_the_draft_already_goes_to_a_person():
    assert objecting_sides(decision("dismissed", review=True), "passenger") == []


def test_an_objection_must_name_a_citable_rule_and_an_existing_record():
    assert check(GOOD, CTX, RULES) is None
    assert "rule" in check({**GOOD, "rule": "made_up.rule"}, CTX, RULES)
    assert "record" in check({**GOOD, "record": "app_events[9]"}, CTX, RULES)
    assert check({**GOOD, "objection": False}, CTX, RULES) == "no objection"
    assert record_exists(CTX, "app_events[1]") and record_exists(CTX, "chat_log[0]")
    assert not record_exists(CTX, "gps_trace[0]")


@pytest.mark.asyncio
async def test_agent_returns_a_checked_objection_and_fails_quiet():
    ok = SimpleNamespace(chat_json=AsyncMock(return_value=json.dumps(GOOD)))
    out = await ObjectionAgent(ok).object("passenger", CTX, decision(), RULES)
    assert out["objection"] is True and out["side"] == "passenger"
    bad = SimpleNamespace(chat_json=AsyncMock(return_value=json.dumps({**GOOD, "rule": "x"})))
    out = await ObjectionAgent(bad).object("passenger", CTX, decision(), RULES)
    assert out["objection"] is False and "rule" in out["dropped"]
    down = SimpleNamespace(chat_json=AsyncMock(side_effect=RuntimeError("down")))
    assert (await ObjectionAgent(down).object("passenger", CTX, decision(), RULES))["objection"] is False


def test_judge_prompt_shows_objections_only_when_given():
    plain = ArbitrationAgent._build_user_prompt({}, {}, {}, {}, [])
    assert "OBJECTIONS TO YOUR DRAFT RULING" not in plain
    with_obj = ArbitrationAgent._build_user_prompt(
        {}, {}, {}, {}, [], None,
        {"draft": {"verdict": "dismissed"}, "objections": [{"side": "passenger", **GOOD}]})
    assert "OBJECTIONS TO YOUR DRAFT RULING" in with_obj and "below the 8-min threshold" in with_obj


# ---- in the graph -------------------------------------------------------
from tests.test_workflow_graph import (  # noqa: E402
    StubFairness, build_graph, initial_state, make_decision)


class TwoPassArbitrator:
    """Draft, then a reconsidered ruling; records what the second call saw."""

    def __init__(self):
        self.calls, self.objection = 0, None
        self.draft = make_decision(verdict=Verdict.DISMISSED, refund_amount=None)
        self.final = make_decision(verdict=Verdict.UPHELD, refund_amount=8.0)

    async def arbitrate(self, context, passenger_analysis, driver_analysis, policy_evaluation,
                        debate_history, precedents=None, objection=None):
        self.calls += 1
        self.objection = objection
        return self.final if objection else self.draft

    _build_valid_refs = staticmethod(lambda policy_evaluation, context: RULES)


class StubObjection:
    def __init__(self, stands=True):
        self.stands, self.calls = stands, 0

    async def object(self, side, context, decision, valid_rules):
        self.calls += 1
        return {"side": side, "objection": self.stands, "claim": GOOD["claim"],
                "rule": GOOD["rule"], "record": GOOD["record"]}


def graph(arbitrator, objection):
    from src.core import workflow as wf
    from src.core.workflow import build_dispute_graph
    import tests.test_workflow_graph as g
    return build_dispute_graph(
        safety_agent=g.StubSafety(), case_brief=g.StubCaseBrief(), collector=g.StubCollector(),
        classifier=g.StubClassifier(), debate_engine=g.StubDebate(), arbitrator=arbitrator,
        fairness_agent=StubFairness(), executor=g.StubExecutor(), objection_agent=objection)


@pytest.mark.asyncio
async def test_a_standing_objection_makes_the_judge_reconsider(monkeypatch):
    from src.core import workflow as wf
    monkeypatch.setattr(wf, "OBJECTION_ROUND", True)
    arb, obj = TwoPassArbitrator(), StubObjection(stands=True)
    final = await graph(arb, obj).ainvoke(initial_state())
    assert arb.calls == 2 and obj.calls == 1
    assert arb.objection["draft"]["verdict"] == "dismissed"
    assert final["decision"].verdict == Verdict.UPHELD and final["draft_decision"].verdict == Verdict.DISMISSED


@pytest.mark.asyncio
async def test_a_dropped_objection_changes_nothing(monkeypatch):
    from src.core import workflow as wf
    monkeypatch.setattr(wf, "OBJECTION_ROUND", True)
    arb = TwoPassArbitrator()
    final = await graph(arb, StubObjection(stands=False)).ainvoke(initial_state())
    assert arb.calls == 1 and final["decision"].verdict == Verdict.DISMISSED
    assert final["objections"][0]["objection"] is False


@pytest.mark.asyncio
async def test_switched_off_by_default(monkeypatch):
    from src.core import workflow as wf
    monkeypatch.setattr(wf, "OBJECTION_ROUND", False)
    arb, obj = TwoPassArbitrator(), StubObjection()
    await graph(arb, obj).ainvoke(initial_state())
    assert arb.calls == 1 and obj.calls == 0
