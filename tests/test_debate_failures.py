"""D54: a failed advocate turn is retried once; if it still fails, the case goes to a person."""
import pytest

from src.core import debate as debate_mod
from src.agents.fairness import FairnessAgent, FairnessIssueCode, _advocate_ran
from tests.test_fairness_agent import FakeLLMClient, make_input, make_passenger_analysis

FAILED_ANALYSIS = {"stance": "", "evidence": [], "reasoning": "LLM call failed: 429 queue_exceeded",
                   "confidence": 0.0, "requires_human_review": True, "failed": True}
FAILED_REBUTTAL = ("The driver's rebuttal could not be generated automatically. "
                   "Reason: LLM returned empty output. This argument requires human review.")


@pytest.mark.asyncio
async def test_a_failed_turn_is_retried_once():
    replies = [FAILED_ANALYSIS, {"stance": "refund", "reasoning": "r", "evidence": ["x"]}]
    calls = []

    async def call():
        calls.append(1)
        return replies[len(calls) - 1]

    out = await debate_mod._with_one_retry(call)
    assert len(calls) == 2 and out["stance"] == "refund"


@pytest.mark.asyncio
async def test_a_turn_that_fails_twice_is_returned_as_failed_and_a_good_turn_is_not_retried():
    calls = []

    async def bad():
        calls.append(1)
        return FAILED_REBUTTAL

    assert await debate_mod._with_one_retry(bad) == FAILED_REBUTTAL and len(calls) == 2
    calls.clear()

    async def good():
        calls.append(1)
        return "The rider cancelled before the updated ETA."

    await debate_mod._with_one_retry(good)
    assert len(calls) == 1


def test_a_failed_opening_does_not_count_as_heard():
    # Before D54 the error text in "reasoning" made a failed advocate look heard (F2-15)
    assert _advocate_ran(FAILED_ANALYSIS) is False
    assert _advocate_ran(make_passenger_analysis()) is True


@pytest.mark.asyncio
async def test_fairness_escalates_a_failed_opening():
    a = await FairnessAgent(llm_client=FakeLLMClient()).assess(make_input(passenger_analysis=FAILED_ANALYSIS))
    assert FairnessIssueCode.ONE_SIDE_NOT_CONSIDERED in {i.code for i in a.issues}
    assert a.requires_human_review is True


@pytest.mark.asyncio
async def test_fairness_escalates_a_missing_rebuttal():
    inp = make_input()
    history = list(inp.debate_history) + [{"round": 1, "speaker": "passenger", "content": "Rider rebuttal."},
                                          {"round": 1, "speaker": "driver", "content": FAILED_REBUTTAL}]
    a = await FairnessAgent(llm_client=FakeLLMClient()).assess(make_input(debate_history=history))
    issue = next(i for i in a.issues if i.code == FairnessIssueCode.ONE_SIDE_NOT_CONSIDERED)
    assert "driver (round 1)" in issue.description and a.requires_human_review is True
