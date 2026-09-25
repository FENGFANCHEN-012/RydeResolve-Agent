"""A daily provider quota error must stop before more agent requests are sent."""
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from src.core.debate import DebateEngine


def engine_with_agents(passenger_opening={"reasoning": "ok"}, driver_rebuttal="ok"):
    # Avoid initialising real retrievers or LLM clients; only exercise orchestration.
    engine = object.__new__(DebateEngine)
    engine.max_rounds = 3
    engine.passenger_agent = SimpleNamespace(
        analyze=AsyncMock(return_value=passenger_opening),
        rebut=AsyncMock(return_value="Passenger response"),
    )
    engine.driver_agent = SimpleNamespace(
        analyze=AsyncMock(return_value={"reasoning": "ok"}),
        rebut=AsyncMock(return_value=driver_rebuttal),
    )
    engine.policy_agent = SimpleNamespace(
        evaluate_compliance=AsyncMock(return_value={"reasoning": "ok"}),
    )
    return engine


@pytest.mark.asyncio
async def test_groq_token_quota_stops_after_failed_rebuttal():
    error = "LLM call failed: Error code: 429 - rate_limit_exceeded on tokens per day (TPD)"
    engine = engine_with_agents(driver_rebuttal=error)

    with pytest.raises(RuntimeError, match="daily quota exhausted"):
        await engine.debate(object())

    engine.passenger_agent.rebut.assert_awaited_once()
    engine.driver_agent.rebut.assert_awaited_once()


@pytest.mark.asyncio
async def test_gemini_request_quota_stops_before_next_agent():
    engine = engine_with_agents(
        passenger_opening={"reasoning": "LLM call failed: GenerateRequestsPerDay 429"}
    )

    with pytest.raises(RuntimeError, match="daily quota exhausted"):
        await engine.debate(object())

    engine.driver_agent.analyze.assert_not_awaited()
    engine.policy_agent.evaluate_compliance.assert_not_awaited()
