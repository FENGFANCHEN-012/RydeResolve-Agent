"""D26: the LLM complexity hint can only raise a simple, safe case."""
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from src.agents.collector import DisputeContext, DisputeType
from src.agents.complexity import ComplexityAgent
from src.core.triage import apply_hint, needs_hint, triage

SIMPLE = {"complexity": "simple", "risk": "safe", "max_rounds": 1, "fairness_llm_audit": False,
          "advocate_research": False, "reasons": ["no complexity or risk signal"]}


def ctx():
    return DisputeContext(dispute_id="T", type=DisputeType.ROUTE_DEVIATION, reporter="passenger", order_id="O",
                          description="charged more", chat_log=[{"sender": "driver", "message": "via SLE ok?"}],
                          case_brief={"dispute_type": "route_deviation", "facts": []})


def test_hint_raises_a_simple_case_with_its_reason():
    g = apply_hint(SIMPLE, {"level": "complex", "kind": "causes", "reason": "stop and detour both added distance"})
    assert g["complexity"] == "complex" and g["advocate_research"] and g["fairness_llm_audit"]
    assert g["raised_by_hint"] and g["reasons"] == ["LLM hint (causes): stop and detour both added distance"]


def test_hint_never_lowers_or_touches_other_grades():
    assert apply_hint(SIMPLE, {"level": "simple"}) is SIMPLE
    assert apply_hint(SIMPLE, {"level": None}) is SIMPLE
    complex_ = {**SIMPLE, "complexity": "complex"}
    dangerous = {**SIMPLE, "risk": "dangerous"}
    assert apply_hint(complex_, {"level": "simple"}) is complex_
    assert not needs_hint(complex_) and not needs_hint(dangerous) and needs_hint(SIMPLE)
    # A real code grade keeps its shape after a raise
    code = triage(ctx(), SimpleNamespace(urgency="P2"), {"level": "low"})
    assert set(apply_hint(code, {"level": "complex", "kind": "order", "reason": "x"})) >= set(code)


@pytest.mark.asyncio
async def test_agent_parses_and_requires_a_named_kind():
    def agent(reply):
        return ComplexityAgent(llm_client=SimpleNamespace(chat_json=AsyncMock(return_value=reply)))
    h = await agent(json.dumps({"level": "complex", "kind": "consent", "reason": "ok covered the route only"})).hint(ctx())
    assert h == {"level": "complex", "kind": "consent", "reason": "ok covered the route only"}
    h = await agent(json.dumps({"level": "complex", "kind": None, "reason": "hard"})).hint(ctx())
    assert h["level"] == "simple" and h["noted_not_raised"]
    # A rule "conflict" is noted but does not raise (general rule + exception misread, D26 probe)
    h = await agent(json.dumps({"level": "complex", "kind": "rules", "reason": "fee vs waiver"})).hint(ctx())
    assert h["level"] == "simple" and h["kind"] == "rules" and h["noted_not_raised"]
    prompt = agent("{}")._llm.chat_json
    await ComplexityAgent(llm_client=SimpleNamespace(chat_json=prompt)).hint(ctx())
    assert "chat_log[0] driver: via SLE ok?" in prompt.call_args.kwargs["messages"][1]["content"]


@pytest.mark.asyncio
async def test_failed_hint_keeps_the_code_grade():
    llm = SimpleNamespace(chat_json=AsyncMock(side_effect=RuntimeError("429")))
    h = await ComplexityAgent(llm_client=llm).hint(ctx())
    assert h["level"] is None and apply_hint(SIMPLE, h) is SIMPLE
