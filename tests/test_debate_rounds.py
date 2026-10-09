"""Triage round cap (D24 on main): a second round runs only if a side raised a new point."""
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from src.core.debate import NEW_POINT_INSTRUCTION, DebateEngine, split_new_point


def engine(passenger_rebuttals, driver_rebuttals):
    # No real retrievers or LLM clients; only the round logic is exercised.
    eng = object.__new__(DebateEngine)
    eng.max_rounds = 1
    eng.passenger_agent = SimpleNamespace(analyze=AsyncMock(return_value={"reasoning": "ok"}),
                                          rebut=AsyncMock(side_effect=passenger_rebuttals))
    eng.driver_agent = SimpleNamespace(analyze=AsyncMock(return_value={"reasoning": "ok"}),
                                       rebut=AsyncMock(side_effect=driver_rebuttals))
    eng.policy_agent = SimpleNamespace(evaluate_compliance=AsyncMock(return_value={"reasoning": "ok"}))
    return eng


def rounds_run(history):
    return max(h["round"] for h in history)


@pytest.mark.asyncio
async def test_simple_case_runs_one_round_and_asks_for_no_tag():
    eng = engine(["P1"], ["D1"])
    history, _ = await eng.debate_with_context(object(), max_rounds=1)
    assert rounds_run(history) == 1
    assert "extra_instruction" not in eng.passenger_agent.rebut.await_args.kwargs


@pytest.mark.asyncio
async def test_complex_case_stops_when_neither_side_has_a_new_point():
    eng = engine(["P1\nNEW_POINT: no"], ["D1\nNEW_POINT: no"])
    history, _ = await eng.debate_with_context(object(), max_rounds=2)
    assert rounds_run(history) == 1
    assert eng.passenger_agent.rebut.await_args.kwargs["extra_instruction"] == NEW_POINT_INSTRUCTION
    # the tag never reaches the other side or the Judge
    assert eng.driver_agent.rebut.await_args.args[0] == "P1"
    assert all("NEW_POINT" not in str(h["content"]) for h in history)


@pytest.mark.asyncio
async def test_complex_case_runs_round_two_when_one_side_has_a_new_point():
    eng = engine(["P1\nNEW_POINT: yes", "P2"], ["D1\nNEW_POINT: no", "D2"])
    history, _ = await eng.debate_with_context(object(), max_rounds=2)
    assert rounds_run(history) == 2
    # the last allowed round asks for no tag
    assert "extra_instruction" not in eng.driver_agent.rebut.await_args.kwargs


def test_split_new_point_reads_and_strips_the_tag():
    assert split_new_point("Text.\n**NEW_POINT: No**") == ("Text.", False)
    assert split_new_point("Text.\nNEW_POINT: yes") == ("Text.", True)
    # no tag, or not text: count as new so a missing answer never cuts the debate short
    assert split_new_point("Text.") == ("Text.", True)
    assert split_new_point({"reasoning": "x"})[1] is True
