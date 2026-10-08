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
    # events_between names events the prompts already show (timeline, chat log) by id only
    text = EvidencePool.render_for_prompt(ctx.evidence_pool)
    assert "app_events[0]" in text and "chat_log[0]" in text and "[E2]" in text
    assert "I'm at the lobby" not in text

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


def test_fetched_topics_are_not_requested_again():
    ctx = make_context()
    ctx.case_brief = {"topics": {"no_show": "core"}, "fetched_topics": ["refund"]}
    from src.agents.research import fetched_topics
    already = fetched_topics(ctx)
    assert valid_topics({"policy_topics": ["no_show", "refund", "waiting_fee"]}, already) == ["waiting_fee"]


def test_pool_shows_old_items_as_one_line():
    from src.core.evidence_pool import EvidencePoolItem
    from src.agents.collector_tools import Finding
    items = [EvidencePoolItem.from_collector_tool("driver", "gps_at", {"timestamp": f"T{i}"},
             [Finding(id="x", tool="gps_at", kind="fact", statement=f"statement {i} " + "x" * 300)])
             for i in range(6)]
    pool = EvidencePool.merge_pools([], items)
    compact = EvidencePool.render_for_prompt(pool)            # advocates: newest 4 in full
    full = EvidencePool.render_for_prompt(pool, full_last=None)  # Judge
    assert "[E1] (driver) statement 0" in compact and "asked by driver" not in compact.split("[E3]")[0]
    assert compact.count("asked by") == 4 and full.count("asked by") == 6
    assert len(compact) < len(full)


@pytest.mark.asyncio
async def test_rebuttal_research_skipped_when_other_side_added_nothing(monkeypatch):
    calls = []

    async def fake_research(side, context, llm, retriever, round_num, debate_so_far):
        calls.append((side, round_num))
        if (side, round_num) == ("driver", 0):   # only the driver finds something, at the opening
            from src.core.evidence_pool import EvidencePoolItem
            from src.agents.collector_tools import Finding
            item = EvidencePoolItem.from_collector_tool("driver", "gps_at", {"timestamp": T0},
                                                       [Finding(id="g", tool="gps_at", kind="fact", statement="s")])
            context.evidence_pool = EvidencePool.merge_pools(context.evidence_pool, [item])
        return context, {"added_evidence": []}

    monkeypatch.setattr("src.core.debate.research_turn", fake_research)
    monkeypatch.setattr("src.core.debate.QueryPlanner",
                        lambda agent_name: SimpleNamespace(auto_query=AsyncMock(return_value=[])))
    engine = object.__new__(DebateEngine)
    engine.max_rounds = 1
    engine.passenger_agent = SimpleNamespace(analyze=AsyncMock(return_value={"reasoning": "p"}),
                                             rebut=AsyncMock(return_value="p"))
    engine.driver_agent = SimpleNamespace(analyze=AsyncMock(return_value={"reasoning": "d"}),
                                          rebut=AsyncMock(return_value="d"))
    engine.policy_agent = SimpleNamespace(evaluate_compliance=AsyncMock(return_value={}),
                                          _get_retriever=lambda: None)
    await engine.debate_with_context(make_context())
    # Passenger looks again in round 1 (the driver added E1); the driver does not (nothing new)
    assert calls == [("passenger", 0), ("driver", 0), ("passenger", 1)]


def test_events_between_gives_text_beyond_the_timeline():
    from src.agents.collector_tools import BRIEF_TIMELINE_EVENTS, events_between
    ctx = make_context()
    ctx.app_events = [{"timestamp": f"2026-09-21T09:{i:02d}:00+08:00", "event_type": f"e{i}",
                       "details": f"detail {i}"} for i in range(BRIEF_TIMELINE_EVENTS + 2)]
    stmt = events_between(ctx, "2026-09-21T09:00:00+08:00", "2026-09-21T09:30:00+08:00")[0].statement
    assert "app_events[0]" in stmt and "detail 0" not in stmt                 # in the timeline
    assert f"detail {BRIEF_TIMELINE_EVENTS + 1}" in stmt                      # beyond it: full text


@pytest.mark.asyncio
async def test_extra_round_only_if_previous_round_added_evidence(monkeypatch):
    monkeypatch.setattr("src.core.debate.ADVOCATE_RESEARCH", False)   # no lookups at all
    engine = object.__new__(DebateEngine)
    engine.max_rounds = 1
    engine.passenger_agent = SimpleNamespace(analyze=AsyncMock(return_value={"reasoning": "p"}),
                                             rebut=AsyncMock(return_value="p"))
    engine.driver_agent = SimpleNamespace(analyze=AsyncMock(return_value={"reasoning": "d"}),
                                          rebut=AsyncMock(return_value="d"))
    engine.policy_agent = SimpleNamespace(evaluate_compliance=AsyncMock(return_value={}),
                                          _get_retriever=lambda: None)
    history, _ = await engine.debate_with_context(make_context(), max_rounds=3)
    # Round 1 always runs; round 2 does not, since round 1 found nothing new
    assert [h["round"] for h in history] == [0, 0, 0, 1, 1]


@pytest.mark.asyncio
async def test_step3b_self_concession_dropped_and_both_done_stops(monkeypatch):
    monkeypatch.setattr("src.core.debate.ADVOCATE_RESEARCH", False)
    import json as _j
    p = _j.dumps({"moves": [{"type": "concede", "target": "D1", "text": "own", "cites": ["E1"]},
                            {"type": "claim", "target": "", "text": "x", "cites": ["E1"]}], "done": True})
    d = _j.dumps({"moves": [{"type": "claim", "target": "", "text": "y", "cites": ["E1"]}], "done": True})
    engine = object.__new__(DebateEngine)
    engine.max_rounds = 1
    engine.passenger_agent = SimpleNamespace(analyze=AsyncMock(return_value={"reasoning": "p"}),
                                             rebut=AsyncMock(return_value=p))
    engine.driver_agent = SimpleNamespace(analyze=AsyncMock(return_value={"reasoning": "d"}),
                                          rebut=AsyncMock(return_value=d))
    engine.policy_agent = SimpleNamespace(evaluate_compliance=AsyncMock(return_value={}),
                                          _get_retriever=lambda: None)
    history, _ = await engine.debate_with_context(make_context(), max_rounds=3)
    assert [m["type"] for m in history[3]["moves"]] == ["claim"]     # D1 is the passenger's own turn
    assert max(h["round"] for h in history) == 1                    # both done: no second round
