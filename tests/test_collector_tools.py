"""
Tests for the Collector's deterministic tools (src/agents/collector_tools.py).
"""
import copy
import json
import os
import re
import sys
from pathlib import Path

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from src.agents import collector_tools
from src.agents.collector import CollectorAgent
from src.core.trace import Tracer, set_tracer, step

MOCK_DIR = Path(__file__).resolve().parent.parent / "data" / "mock_disputes"


def _load(name: str) -> dict:
    return json.loads((MOCK_DIR / f"{name}.json").read_text(encoding="utf-8"))


async def _ctx(name: str, mutate=None):
    data = _load(name)
    if mutate:
        mutate(data)
    return await CollectorAgent().collect_from_dataset(data)


def _by_id(ctx) -> dict:
    return {f.id: f for f in ctx.findings}


# ---------------------------------------------------------------------- #
# Facts on the real mock cases
# ---------------------------------------------------------------------- #

@pytest.mark.asyncio
async def test_no_show_01_driver_never_arrived():
    f = _by_id(await _ctx("no_show_01"))
    assert f["pickup_proximity.at_cancellation"].value["distance_km"] == pytest.approx(1.77, abs=0.02)
    assert f["consistency.no_show_without_arrival"].kind == "conflict"
    assert f["contact_attempts.rider"].value == {"messages": 3, "calls": 1}
    assert f["contact_attempts.driver"].value == {"messages": 0, "calls": 0}


@pytest.mark.asyncio
async def test_no_show_02_driver_waited_at_pickup():
    ctx = await _ctx("no_show_02")
    f = _by_id(ctx)
    assert f["wait_time.waited_before_cancel"].value["minutes_waited"] == 8.0
    assert f["pickup_proximity.nearest"].value["nearest_km"] == 0.0
    assert not [x for x in ctx.findings if x.kind == "conflict"]


@pytest.mark.asyncio
async def test_no_show_03_gps_gap_is_reported():
    f = _by_id(await _ctx("no_show_03"))
    assert "gps_trace" in f["data_gaps.missing_sources"].value["missing"]
    assert f["data_gaps.gps_signal_lost"].kind == "gap"
    assert "pickup_proximity.nearest" not in f  # nothing to measure without GPS


@pytest.mark.asyncio
async def test_surge_timing_relative_to_booking():
    f1 = _by_id(await _ctx("fare_dispute_01"))["fare_check.surge_timing"].value["events"]
    assert {"event": "surge_multiplier_changed", "relative_to_booking": "after"} in f1
    f2 = _by_id(await _ctx("fare_dispute_02"))["fare_check.surge_timing"].value["events"]
    assert {"event": "rider_accepted_surge", "relative_to_booking": "before"} in f2


@pytest.mark.asyncio
async def test_route_and_speed():
    f = _by_id(await _ctx("route_deviation_01"))
    assert f["route_check.distance"].value["deviation_percent"] == 26.8
    assert "route_check.reported_deviation_mismatch" not in f
    s = _by_id(await _ctx("service_quality_01"))["speed_profile.max"].value
    assert s["max_speed_kmh"] == 104 and s["alerts"] == 3


@pytest.mark.asyncio
async def test_completed_trip_has_no_pickup_proximity_noise():
    assert "pickup_proximity.nearest" not in _by_id(await _ctx("fare_dispute_01"))


# ---------------------------------------------------------------------- #
# Conflicts (mock data edited to create them)
# ---------------------------------------------------------------------- #

@pytest.mark.asyncio
async def test_arrival_event_far_from_pickup_is_a_conflict():
    def move_driver(d):
        for p in d["gps_telemetry"]:
            p["lat"] += 0.02  # ~2.2 km north
    f = _by_id(await _ctx("no_show_02", move_driver))
    assert f["consistency.arrival_gps_far"].value["distance_km"] > 2


@pytest.mark.asyncio
async def test_fare_breakdown_and_route_and_fee_mismatches():
    def bad_fare(d):
        d["trip_data"]["fare_breakdown"]["base_fare"] += 1
        d["trip_data"]["fare_breakdown"]["total"] = 99.0
    f = _by_id(await _ctx("fare_dispute_01", bad_fare))
    assert "fare_check.subtotal_mismatch" in f and "fare_check.total_mismatch" in f

    def bad_route(d):
        d["trip_data"]["route_deviation_percent"] = 5.0
    assert "route_check.reported_deviation_mismatch" in _by_id(await _ctx("route_deviation_01", bad_route))

    def bad_fee(d):
        d["trip_data"]["cancellation_fee"] = 12.0
    assert "fee_check.policy_amount_mismatch" in _by_id(await _ctx("no_show_02", bad_fee))


# ---------------------------------------------------------------------- #
# Every case: sources are real, output is stable
# ---------------------------------------------------------------------- #

_INDEXED = re.compile(r"^(gps_trace|chat_log|app_events)\[(\d+)\]$")


@pytest.mark.asyncio
@pytest.mark.parametrize("path", sorted(MOCK_DIR.glob("*.json")), ids=lambda p: p.stem)
async def test_every_source_reference_exists(path):
    ctx = await CollectorAgent().collect_from_dataset(path)
    assert ctx.findings, "every case should produce at least one finding"
    for f in ctx.findings:
        for src in f.sources:
            m = _INDEXED.match(src)
            if m:
                assert int(m.group(2)) < len(getattr(ctx, m.group(1)) or []), f"{f.id}: {src}"


@pytest.mark.asyncio
async def test_findings_are_deterministic():
    a = await _ctx("no_show_01")
    b = await _ctx("no_show_01")
    assert [f.model_dump() for f in a.findings] == [f.model_dump() for f in b.findings]


# ---------------------------------------------------------------------- #
# Query tools, failure isolation, trace events
# ---------------------------------------------------------------------- #

@pytest.mark.asyncio
async def test_query_gps_at_and_events_between():
    agent = CollectorAgent()
    ctx = await agent.collect_from_dataset(_load("no_show_01"))
    g = agent.query(ctx, "gps_at", timestamp="2026-09-21T09:08:30+08:00")[0]
    assert g.value["gps_timestamp"] == "2026-09-21T09:08:00+08:00"
    assert g.value["distance_to_pickup_km"] == pytest.approx(1.77, abs=0.02)
    ev = agent.query(ctx, "events_between", start="2026-09-21T09:04:00+08:00", end="2026-09-21T09:07:00+08:00")[0]
    assert len(ev.value["events"]) == 3
    with pytest.raises(ValueError):
        agent.query(ctx, "delete_everything")


@pytest.mark.asyncio
async def test_failing_tool_does_not_stop_collection(monkeypatch):
    def boom(ctx):
        raise RuntimeError("bad field")
    monkeypatch.setitem(collector_tools.STANDARD_TOOLS, "fare_check", boom)
    f = _by_id(await _ctx("fare_dispute_01"))
    assert f["fare_check.error"].kind == "gap"
    assert "route_check.distance" in f  # other tools still ran


@pytest.mark.asyncio
async def test_tool_calls_are_traced():
    tracer = Tracer()
    set_tracer(tracer)
    try:
        async with step("Collector", "Collect"):
            await _ctx("no_show_01")
    finally:
        set_tracer(None)
    calls = [e for e in tracer.events if e["type"] == "tool_call"]
    assert [c["tool"] for c in calls] == list(collector_tools.STANDARD_TOOLS)
    assert all(c["step_id"] == "s1" for c in calls)
    assert not [e for e in tracer.events if e["type"] == "llm_call"]


@pytest.mark.asyncio
async def test_raw_data_is_not_modified():
    data = _load("no_show_01")
    before = copy.deepcopy(data)
    await CollectorAgent().collect_from_dataset(data)
    before.pop("expected_outcome")
    data.pop("_source", None)
    data.pop("expected_outcome", None)
    assert data == before
