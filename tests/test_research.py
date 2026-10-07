"""D23: advocates choose their own lookups; pools are numbered and shared."""
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from src.agents.collector import DisputeContext, DisputeType
from src.agents.research import render_debate, research_turn, valid_lookups, valid_topics
from src.core.debate import DebateEngine
from src.core.evidence_pool import EvidencePool

T0 = "2026-09-21T09:00:00+08:00"


def make_context() -> DisputeContext:
    return DisputeContext(
        dispute_id="T-NS-1", type=DisputeType.NO_SHOW, reporter="driver", order_id="RYDE-T-1",
        description="Rider never came out.",
        trip={"pickup_location": {"lat": 1.30, "lng": 103.80}},
        gps_trace=[{"timestamp": "2026-09-21T09:00:00+08:00", "lat": 1.3001, "lng": 103.8001,
                    "status": "waiting", "speed_kmh": 0},
                   {"timestamp": "2026-09-21T09:06:00+08:00", "lat": 1.3001, "lng": 103.8001,
                    "status": "waiting", "speed_kmh": 0}],
        app_events=[{"timestamp": "2026-09-21T09:00:30+08:00", "event_type": "driver_arrived",
                     "details": "Driver pressed I'm Here"},
                    {"timestamp": "2026-09-21T09:08:00+08:00", "event_type": "trip_cancelled",
                     "details": "Driver cancelled"}],
        chat_log=[{"timestamp": "2026-09-21T09:02:00+08:00", "sender": "driver",
                   "message": "I'm at the lobby", "message_type": "text"}],
    )


def llm_returning(plan: dict):
    return SimpleNamespace(chat_json=AsyncMock(return_value=json.dumps(plan)))


def test_valid_lookups_drop_bad_tools_and_args_and_cap():
    plan = {"lookups": [
        {"tool": "gps_at", "args": {"timestamp": T0}, "why": "where was the car"},
        {"tool": "rm_rf", "args": {}},
        {"tool": "events_between", "args": {"start": T0}},           # missing end
        {"tool": "events_between", "args": {"start": T0, "end": T0, "x": 1}},
        {"tool": "gps_at", "args": {"timestamp": T0}},
    ]}
    out = valid_lookups(plan)
    assert [t for t, _, _ in out] == ["gps_at", "events_between"]
    assert out[1][1] == {"start": T0, "end": T0}                     # extra args stripped


def test_valid_topics_catalogue_only():
    assert valid_topics({"policy_topics": ["no_show", "made_up", "NO_SHOW", "refund", "waiting_fee"]}) \
        == ["no_show", "refund"]


@pytest.mark.asyncio
async def test_research_turn_runs_lookups_into_numbered_pool():
    ctx = make_context()
    llm = llm_returning({"lookups": [
        {"tool": "events_between", "args": {"start": T0, "end": "2026-09-21T09:10:00+08:00"},
         "why": "show the wait"},
        {"tool": "gps_at", "args": {"timestamp": "2026-09-21T09:05:00+08:00"}, "why": "car position"}]})
    ctx, record = await research_turn("driver", ctx, llm, retriever=None, round_num=0)
    assert record["added_evidence"] == ["E1", "E2"]
    first = ctx.evidence_pool[0]
    assert first["source_agent"] == "driver" and first["why"] == "show the wait"
    # events_between now states the events themselves, not just a count
    text = EvidencePool.render_for_prompt(ctx.evidence_pool)
    assert "driver_arrived" in text and "I'm at the lobby" in text and "[E2]" in text

    # The other side asking for the same lookup does not duplicate it
    ctx, record = await research_turn("passenger", ctx, llm, retriever=None, round_num=1)
    assert record["added_evidence"] == [] and len(ctx.evidence_pool) == 2


@pytest.mark.asyncio
async def test_research_turn_survives_bad_llm_output():
    ctx = make_context()
    llm = SimpleNamespace(chat_json=AsyncMock(return_value="not json"))
    ctx, record = await research_turn("passenger", ctx, llm)
    assert ctx.evidence_pool == [] and record["added_evidence"] == []
    llm = SimpleNamespace(chat_json=AsyncMock(side_effect=RuntimeError("boom")))
    ctx, record = await research_turn("passenger", ctx, llm)
    assert "boom" in record["error"]


def test_unknown_evidence_refs():
    pool = [{"item_id": "E1"}, {"item_id": "E2"}]
    assert EvidencePool.unknown_refs("Per [E1] and E7, and [E2].", pool) == ["E7"]


def test_render_debate_numbers_and_speakers():
    text = render_debate([{"id": "D1", "round": 0, "speaker": "passenger",
                           "content": {"stance": "refund", "reasoning": "late"}},
                          {"id": "D4", "round": 1, "speaker": "driver", "content": "No, see [E1]."}])
    assert "[D1] passenger (round 0): refund late" in text and "[D4] driver (round 1)" in text


@pytest.mark.asyncio
async def test_debate_numbers_every_turn(monkeypatch):
    monkeypatch.setattr("src.core.debate.ADVOCATE_RESEARCH", False)
    engine = object.__new__(DebateEngine)
    engine.max_rounds = 1
    engine.passenger_agent = SimpleNamespace(analyze=AsyncMock(return_value={"reasoning": "p"}),
                                             rebut=AsyncMock(return_value="p rebut"))
    engine.driver_agent = SimpleNamespace(analyze=AsyncMock(return_value={"reasoning": "d"}),
                                          rebut=AsyncMock(return_value="d rebut"))
    engine.policy_agent = SimpleNamespace(evaluate_compliance=AsyncMock(return_value={"reasoning": "ok"}),
                                          _get_retriever=lambda: None)
    history, _ = await engine.debate_with_context(make_context())
    assert [(h["id"], h["speaker"]) for h in history] == [
        ("D1", "passenger"), ("D2", "driver"), ("D3", "policy"), ("D4", "passenger"), ("D5", "driver")]
    # The rebuttal sees the numbered debate so far
    assert "[D2] driver" in engine.passenger_agent.rebut.call_args.kwargs["debate_so_far"]
