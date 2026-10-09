"""D24 step 4: Safety agent tiers; code floor the LLM cannot lower; fail safe."""
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from src.agents.collector import DisputeContext, DisputeType
from src.agents.safety import IMMINENT, LEGAL, VERBAL_ABUSE, SafetyAgent, code_floor


def ctx(desc, chat=()):
    return DisputeContext(dispute_id="S", type=DisputeType.SERVICE_QUALITY, reporter="passenger", order_id="O",
                          description=desc, chat_log=[{"sender": "driver", "message": m} for m in chat] or None)


def llm(tier):
    return SimpleNamespace(chat_json=AsyncMock(return_value=json.dumps({"tier": tier, "why": "w"})))


@pytest.mark.asyncio
async def test_si001_style_stalking_is_imminent_in_code_without_llm():
    c = ctx("The driver kept commenting on my body. This is harassment.",
            ["Why you never reply? I know where you stay already haha"])
    model = llm("minor")
    out = await SafetyAgent(model).assess(c)
    assert out["tier"] == IMMINENT and out["decided_by"] == "code" and out["human_review"] == "now"
    model.chat_json.assert_not_awaited()          # the LLM cannot lower a code-decided tier


def test_legal_wording_goes_to_a_person():
    assert code_floor(ctx("I will file a police report and sue Ryde."))["tier"] == LEGAL


@pytest.mark.asyncio
async def test_vague_threat_goes_to_llm_and_verbal_abuse_continues():
    out = await SafetyAgent(llm("verbal_abuse")).assess(ctx("The driver threatened me over the fee."),
                                                        {"safety_alerts": ["you will regret this"]})
    assert out["tier"] == VERBAL_ABUSE and out["human_review"] == "after"
    assert "do_not_rematch_pair" in out["actions"] and out["recommended_only"]


@pytest.mark.asyncio
async def test_llm_failure_or_nonsense_is_imminent():
    bad = SimpleNamespace(chat_json=AsyncMock(side_effect=RuntimeError("down")))
    assert (await SafetyAgent(bad).assess(ctx("He threatened me.")))["tier"] == IMMINENT
    assert (await SafetyAgent(llm("relax")).assess(ctx("He threatened me.")))["tier"] == IMMINENT
