"""
Complex dispute end-to-end tests.

5 elaborate cases that mix multiple conflicts, data gaps and edge conditions.
Each case verifies:
  1. QueryPlanner triggers the right auto-queries
  2. EvidencePool accumulates results from both advocates
  3. The shared pool is visible in both agents' prompts
"""
import json
import sys
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

sys.path.insert(0, ".")

from src.agents.collector import DisputeContext, DisputeType, Finding
from src.agents.collector_tools import Finding as ToolFinding
from src.agents.passenger import PassengerAgent
from src.agents.driver import DriverAgent
from src.agents.query_planner import QueryPlanner
from src.core.evidence_pool import EvidencePool, EvidencePoolItem


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _ts(hour: int, minute: int) -> str:
    return f"2026-09-21T{hour:02d}:{minute:02d}:00+08:00"


def make_mock_retriever(clauses: list[dict] | None = None) -> MagicMock:
    retriever = MagicMock()
    retriever.retrieve_for_dispute.return_value = clauses or []
    return retriever


def make_mock_llm_json(response_text: str = "{}") -> AsyncMock:
    llm = AsyncMock()
    llm.chat_json = AsyncMock(return_value=response_text)
    return llm


def _extract_user_prompt(llm: AsyncMock) -> str:
    call_args = llm.chat_json.call_args
    if call_args is None:
        return ""
    messages = call_args.kwargs.get("messages", call_args.args[0] if call_args.args else [])
    for m in messages:
        if m.get("role") == "user":
            return m.get("content", "")
    return ""


# ---------------------------------------------------------------------------
# Case 1 – No-Show with GPS gap + contested arrival + cancellation fee
# ---------------------------------------------------------------------------

def _case1_no_show_gps_gap() -> DisputeContext:
    """
    Passenger: driver never arrived, charged $3.50 cancellation fee.
    Platform: cancellation_reason='rider_no_show', no arrival event.
    GPS: last signal 8 min before scheduled pickup, then gap.
    """
    return DisputeContext(
        dispute_id="COMPLEX-001",
        type=DisputeType.NO_SHOW,
        reporter="passenger",
        order_id="RYDE-C001",
        description="Driver never arrived. I waited 10 minutes and was charged a fee.",
        trip={
            "scheduled_time": _ts(9, 0),
            "cancellation_time": _ts(9, 10),
            "cancellation_reason": "rider_no_show",
            "cancellation_fee": 3.50,
            "pickup_location": {"lat": 1.2975, "lng": 103.8535},
        },
        app_events=[
            {"timestamp": _ts(8, 55), "event_type": "booking_confirmed"},
            {"timestamp": _ts(8, 57), "event_type": "driver_assigned"},
            {"timestamp": _ts(9, 10), "event_type": "trip_cancelled", "details": {"reason": "rider_no_show"}},
        ],
        gps_trace=[
            {"timestamp": _ts(8, 52), "lat": 1.2900, "lng": 103.8600, "status": "en_route"},
            {"timestamp": _ts(8, 55), "lat": 1.2920, "lng": 103.8580, "status": "en_route"},
            # Gap: no GPS from 8:55 to 9:10
        ],
        chat_log=[
            {"timestamp": _ts(9, 2), "sender": "passenger", "message": "Where are you?"},
            {"timestamp": _ts(9, 5), "sender": "passenger", "message": "I've been waiting 5 min"},
        ],
        payment={"currency": "SGD", "cancellation_fee": 3.50},
        findings=[
            Finding(
                id="consistency.no_show_without_arrival",
                tool="consistency_check",
                kind="conflict",
                statement="Trip cancelled as rider no-show, but no driver arrival event exists.",
                sources=["trip.cancellation_reason", "app_events"],
            ),
            Finding(
                id="data_gaps.gps_signal_lost",
                tool="data_gaps",
                kind="gap",
                statement="GPS signal lost for 15 min before cancellation.",
                sources=["gps_trace"],
            ),
            Finding(
                id="pickup_proximity.nearest",
                tool="pickup_proximity",
                kind="fact",
                statement="Nearest GPS point was 0.95 km from pickup.",
                value={"nearest_km": 0.95},
                sources=["gps_trace"],
            ),
            Finding(
                id="wait_time.no_arrival",
                tool="wait_time",
                kind="gap",
                statement="No driver arrival timestamp; cannot verify wait time.",
                sources=["trip.driver_arrival_time"],
            ),
        ],
    )


# ---------------------------------------------------------------------------
# Case 2 – Fare dispute with surge timing conflict + route deviation
# ---------------------------------------------------------------------------

def _case2_fare_surge_route() -> DisputeContext:
    """
    Passenger: quoted $12, charged $24. Claims no surge shown.
    Platform: surge x2.0 applied. Events show rider_accepted_surge AFTER booking.
    Also route deviation 20%.
    """
    return DisputeContext(
        dispute_id="COMPLEX-002",
        type=DisputeType.FARE,
        reporter="passenger",
        order_id="RYDE-C002",
        description="I was quoted $12 but charged $24. I never saw surge pricing.",
        trip={
            "scheduled_time": _ts(18, 0),
            "start_time": _ts(18, 5),
            "end_time": _ts(18, 25),
            "estimated_distance_km": 10.0,
            "actual_distance_km": 12.5,
            "route_deviation_percent": 25.0,
            "estimated_fare": 12.0,
            "total_fare": 24.0,
            "fare_breakdown": {
                "subtotal": 20.0,
                "surge_multiplier": 2.0,
                "surge_amount": 10.0,
                "erp": 2.0,
                "total": 24.0,
            },
        },
        app_events=[
            {"timestamp": _ts(17, 58), "event_type": "booking_confirmed"},
            {"timestamp": _ts(17, 58), "event_type": "fare_quote_shown", "details": {"fare": 12.0}},
            {"timestamp": _ts(18, 0), "event_type": "surge_multiplier_changed", "details": {"multiplier": 2.0}},
            {"timestamp": _ts(18, 1), "event_type": "rider_accepted_surge"},
            {"timestamp": _ts(18, 5), "event_type": "trip_started"},
            {"timestamp": _ts(18, 25), "event_type": "trip_completed"},
        ],
        gps_trace=[
            {"timestamp": _ts(18, 5), "lat": 1.3000, "lng": 103.8500},
            {"timestamp": _ts(18, 15), "lat": 1.3100, "lng": 103.8600},
            {"timestamp": _ts(18, 25), "lat": 1.3200, "lng": 103.8700},
        ],
        findings=[
            Finding(
                id="fare_check.surge_timing",
                tool="fare_check",
                kind="fact",
                statement="Surge x2.0 applied after booking confirmed but before rider accepted.",
                sources=["app_events", "trip.fare_breakdown"],
            ),
            Finding(
                id="route_check.distance",
                tool="route_check",
                kind="fact",
                statement="Actual distance 12.5 km vs estimated 10.0 km (+25%).",
                sources=["trip.estimated_distance_km", "trip.actual_distance_km"],
            ),
        ],
    )


# ---------------------------------------------------------------------------
# Case 3 – Route deviation with driver claiming road closure
# ---------------------------------------------------------------------------

def _case3_route_deviation_closure() -> DisputeContext:
    """
    Passenger: driver took 40% longer route, overcharged.
    Driver: road closure, informed rider via chat.
    GPS shows deviation but no official closure data.
    Chat log shows driver mentioned 'detour' but rider didn't explicitly agree.
    """
    return DisputeContext(
        dispute_id="COMPLEX-003",
        type=DisputeType.ROUTE_DEVIATION,
        reporter="passenger",
        order_id="RYDE-C003",
        description="Driver took a much longer route. I was overcharged by $8.",
        trip={
            "scheduled_time": _ts(14, 0),
            "start_time": _ts(14, 5),
            "end_time": _ts(14, 35),
            "estimated_distance_km": 8.0,
            "actual_distance_km": 11.5,
            "route_deviation_percent": 43.75,
            "estimated_fare": 14.0,
            "total_fare": 22.0,
            "driver_reported_reason": "Road closure on planned route",
        },
        app_events=[
            {"timestamp": _ts(14, 5), "event_type": "trip_started"},
            {"timestamp": _ts(14, 10), "event_type": "route_recalculated"},
            {"timestamp": _ts(14, 35), "event_type": "trip_completed"},
        ],
        gps_trace=[
            {"timestamp": _ts(14, 5), "lat": 1.2800, "lng": 103.8500},
            {"timestamp": _ts(14, 15), "lat": 1.2950, "lng": 103.8550},  # off route
            {"timestamp": _ts(14, 25), "lat": 1.3050, "lng": 103.8600},
            {"timestamp": _ts(14, 35), "lat": 1.3150, "lng": 103.8650},
        ],
        chat_log=[
            {"timestamp": _ts(14, 8), "sender": "driver", "message": "There's a road closure, need to take a detour."},
            {"timestamp": _ts(14, 9), "sender": "passenger", "message": "OK just get me there fast."},
        ],
        payment={"currency": "SGD", "estimated_fare": 14.0, "charged_fare": 22.0, "disputed_amount": 8.0},
        findings=[
            Finding(
                id="route_check.distance",
                tool="route_check",
                kind="fact",
                statement="Actual distance 11.5 km vs estimated 8.0 km (+43.75%).",
                sources=["trip"],
            ),
            Finding(
                id="route_check.closure_unverified",
                tool="route_check",
                kind="gap",
                statement="Driver claims road closure but no official data available.",
                sources=["trip.driver_reported_reason"],
            ),
        ],
    )


# ---------------------------------------------------------------------------
# Case 4 – Service quality: multiple safety alerts + conflicting ratings
# ---------------------------------------------------------------------------

def _case4_service_quality_safety() -> DisputeContext:
    """
    Passenger: driver drove dangerously, speeding, harsh braking.
    Platform: multiple safety alerts recorded.
    Driver rating is 4.9 but this trip has speeding_alert + harsh_braking.
    Passenger rated 1 star but driver claims passenger was drunk.
    """
    return DisputeContext(
        dispute_id="COMPLEX-004",
        type=DisputeType.SERVICE_QUALITY,
        reporter="passenger",
        order_id="RYDE-C004",
        description="Driver was speeding and braking hard. I felt unsafe throughout the trip.",
        trip={
            "scheduled_time": _ts(22, 0),
            "start_time": _ts(22, 5),
            "end_time": _ts(22, 20),
            "estimated_distance_km": 6.0,
            "actual_distance_km": 6.2,
            "total_fare": 15.0,
        },
        app_events=[
            {"timestamp": _ts(22, 8), "event_type": "speeding_alert", "details": {"speed_kmh": 85}},
            {"timestamp": _ts(22, 12), "event_type": "harsh_braking_detected", "details": {"deceleration_ms2": 6.5}},
            {"timestamp": _ts(22, 15), "event_type": "speeding_alert", "details": {"speed_kmh": 92}},
            {"timestamp": _ts(22, 18), "event_type": "rider_reported_safety", "details": {"category": "unsafe_driving"}},
        ],
        ratings={
            "rider_rating": 1,
            "driver_rating": 4.9,
            "driver_average_rating": 4.85,
        },
        chat_log=[
            {"timestamp": _ts(22, 10), "sender": "passenger", "message": "Please slow down!"},
            {"timestamp": _ts(22, 11), "sender": "driver", "message": "Don't worry I'm a safe driver."},
        ],
        gps_trace=[
            {"timestamp": _ts(22, 5), "lat": 1.3000, "lng": 103.8500},
            {"timestamp": _ts(22, 10), "lat": 1.3050, "lng": 103.8550},
            {"timestamp": _ts(22, 15), "lat": 1.3100, "lng": 103.8600},
            {"timestamp": _ts(22, 20), "lat": 1.3150, "lng": 103.8650},
        ],
        findings=[
            Finding(
                id="speed_profile.max",
                tool="speed_profile",
                kind="fact",
                statement="Maximum speed 92 km/h in a 60 km/h zone.",
                value={"max_speed_kmh": 92, "speed_limit_kmh": 60},
                sources=["app_events"],
            ),
            Finding(
                id="speed_profile.harsh_braking",
                tool="speed_profile",
                kind="fact",
                statement="Harsh braking detected at 22:12.",
                sources=["app_events"],
            ),
        ],
    )


# ---------------------------------------------------------------------------
# Case 5 – Cancellation refund: driver delayed >10 min, then passenger cancelled
# ---------------------------------------------------------------------------

def _case5_cancellation_driver_delay() -> DisputeContext:
    """
    Passenger: driver was 15 min late, I cancelled, but was charged $4.
    Platform: driver assignment at 8:50, but first GPS movement at 9:08.
    Cancellation at 9:05 (after free window but driver not moving).
    Free cancellation: 3 min after matching. Driver delayed >10 min = free.
    """
    return DisputeContext(
        dispute_id="COMPLEX-005",
        type=DisputeType.CANCELLATION,
        reporter="passenger",
        order_id="RYDE-C005",
        description="Driver was 15 minutes late. I cancelled and was charged $4.",
        trip={
            "scheduled_time": _ts(8, 45),
            "driver_assigned_time": _ts(8, 50),
            "driver_arrival_time": None,
            "cancellation_time": _ts(9, 5),
            "cancellation_reason": "rider_cancelled",
            "cancellation_fee": 4.0,
            "pickup_location": {"lat": 1.2975, "lng": 103.8535},
        },
        app_events=[
            {"timestamp": _ts(8, 45), "event_type": "booking_confirmed"},
            {"timestamp": _ts(8, 50), "event_type": "driver_assigned"},
            {"timestamp": _ts(8, 55), "event_type": "wait_timer_started"},
            {"timestamp": _ts(8, 58), "event_type": "contact_attempt", "details": {"by": "passenger", "type": "chat"}},
            {"timestamp": _ts(9, 5), "event_type": "trip_cancelled", "details": {"reason": "rider_cancelled"}},
        ],
        gps_trace=[
            # Driver assigned at 8:50 but GPS shows no movement until 9:08
            {"timestamp": _ts(8, 50), "lat": 1.2800, "lng": 103.8700, "status": "assigned"},
            {"timestamp": _ts(8, 55), "lat": 1.2800, "lng": 103.8700, "status": "assigned"},
            {"timestamp": _ts(9, 0), "lat": 1.2800, "lng": 103.8700, "status": "assigned"},
            {"timestamp": _ts(9, 5), "lat": 1.2800, "lng": 103.8700, "status": "assigned"},
            {"timestamp": _ts(9, 8), "lat": 1.2850, "lng": 103.8650, "status": "en_route"},
        ],
        chat_log=[
            {"timestamp": _ts(8, 52), "sender": "passenger", "message": "Are you coming?"},
            {"timestamp": _ts(8, 58), "sender": "passenger", "message": "I've been waiting 13 min"},
            {"timestamp": _ts(9, 0), "sender": "driver", "message": "Sorry stuck in traffic"},
        ],
        payment={"currency": "SGD", "cancellation_fee": 4.0},
        findings=[
            Finding(
                id="consistency.arrival_without_event",
                tool="consistency_check",
                kind="conflict",
                statement="Driver assigned at 8:50 but no arrival event by cancellation at 9:05.",
                sources=["app_events", "trip"],
            ),
            Finding(
                id="pickup_proximity.at_cancellation",
                tool="pickup_proximity",
                kind="fact",
                statement="Driver was 2.3 km from pickup at cancellation time.",
                value={"nearest_km": 2.3},
                sources=["gps_trace", "trip.pickup_location"],
            ),
            Finding(
                id="wait_time.elapsed",
                tool="wait_time",
                kind="fact",
                statement="Passenger waited 15 min from scheduled pickup.",
                value={"wait_minutes": 15},
                sources=["trip.scheduled_time", "trip.cancellation_time"],
            ),
        ],
    )


# ---------------------------------------------------------------------------
# Test helpers
# ---------------------------------------------------------------------------

_CASES = [
    ("no_show_gps_gap", _case1_no_show_gps_gap),
    ("fare_surge_route", _case2_fare_surge_route),
    ("route_deviation_closure", _case3_route_deviation_closure),
    ("service_quality_safety", _case4_service_quality_safety),
    ("cancellation_driver_delay", _case5_cancellation_driver_delay),
]


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("name,builder", _CASES)
def test_planner_triggers_queries(name: str, builder):
    """For every complex case the planner must propose at least one query."""
    context = builder()
    planner = QueryPlanner(agent_name="test")
    plans = planner._plan(context)

    assert len(plans) >= 1, f"{name}: planner produced no queries"
    for p in plans:
        assert p.tool in {"gps_at", "events_between"}, f"{name}: unknown tool {p.tool}"
        assert p.reason, f"{name}: query has no reason"


@pytest.mark.parametrize("name,builder", _CASES)
def test_planner_respects_max_limit(name: str, builder):
    """Planner must never propose more than MAX_AUTO_QUERIES."""
    context = builder()
    planner = QueryPlanner(agent_name="test")
    plans = planner._plan(context)
    assert len(plans) <= 3, f"{name}: too many queries ({len(plans)})"


@pytest.mark.parametrize("name,builder", _CASES)
def test_planner_does_not_duplicate(name: str, builder):
    """No two plans should have identical (tool, params)."""
    context = builder()
    planner = QueryPlanner(agent_name="test")
    plans = planner._plan(context)
    keys = [(p.tool, tuple(sorted(p.params.items()))) for p in plans]
    assert len(keys) == len(set(keys)), f"{name}: duplicate queries found"


@pytest.mark.parametrize("name,builder", _CASES)
@pytest.mark.asyncio
async def test_passenger_analyze_deposits_pool(name: str, builder):
    """PassengerAgent.analyze must deposit at least one pool item."""
    llm_response = json.dumps({
        "stance": "s", "evidence": [], "contradictory_evidence": [],
        "missing_evidence": [], "obligations": [], "remedy_requested": "",
        "policy_references": [], "reasoning": "r", "confidence": 0.5,
        "requires_human_review": False,
    })
    sample_clause = {
        "clause": "Test clause for " + name,
        "source": "test.md",
        "section": "Test",
        "chunk_index": 0,
    }
    agent = PassengerAgent(
        llm_client=make_mock_llm_json(llm_response),
        retriever=make_mock_retriever([sample_clause]),
    )

    context = builder()
    assert context.evidence_pool == []

    await agent.analyze(context)

    assert len(context.evidence_pool) >= 1, f"{name}: no pool items deposited"
    for item in context.evidence_pool:
        assert item.get("source_agent") == "passenger"
        assert "item_id" in item
        assert "timestamp" in item


@pytest.mark.parametrize("name,builder", _CASES)
@pytest.mark.asyncio
async def test_driver_sees_passenger_pool_and_deposits_own(name: str, builder):
    """
    DriverAgent.analyze must see passenger pool items in its prompt
    and deposit its own queries.
    """
    llm_response = json.dumps({
        "stance": "s", "evidence": [], "contradictory_evidence": [],
        "missing_evidence": [], "obligations": [], "remedy_requested": "",
        "policy_references": [], "reasoning": "r", "confidence": 0.5,
        "requires_human_review": False,
    })
    sample_clause = {
        "clause": "Test clause for " + name,
        "source": "test.md",
        "section": "Test",
        "chunk_index": 0,
    }
    llm = make_mock_llm_json(llm_response)
    agent = DriverAgent(
        llm_client=llm,
        retriever=make_mock_retriever([sample_clause]),
    )

    context = builder()
    # Pre-populate with a fake passenger query
    context.evidence_pool = [
        EvidencePoolItem.from_collector_tool(
            source_agent="passenger",
            tool_name="events_between",
            params={"start": _ts(8, 50), "end": _ts(9, 10)},
            findings=[ToolFinding(
                id="test.fact", tool="test", kind="fact",
                statement="Passenger found no arrival event.",
            )],
        ).model_dump(),
    ]

    await agent.analyze(context)

    # Driver should have added its own items
    driver_items = [i for i in context.evidence_pool if i.get("source_agent") == "driver"]
    assert len(driver_items) >= 1, f"{name}: driver deposited no items"

    # The prompt must contain the passenger's pool item
    user_prompt = _extract_user_prompt(llm)
    assert "SHARED EVIDENCE POOL" in user_prompt, f"{name}: pool not in prompt"
    assert "Passenger found no arrival event." in user_prompt, f"{name}: passenger finding not visible"


@pytest.mark.parametrize("name,builder", _CASES)
def test_evidence_pool_merge_no_duplicates(name: str, builder):
    """Merging the same item twice must not duplicate it."""
    context = builder()
    item = EvidencePoolItem.from_collector_tool(
        source_agent="passenger",
        tool_name="gps_at",
        params={"timestamp": _ts(9, 0)},
        findings=[],
    )
    context.evidence_pool = [item.model_dump()]
    merged = EvidencePool.merge_pools(context.evidence_pool, [item])
    assert len(merged) == 1, f"{name}: duplicate after merge"


@pytest.mark.parametrize("name,builder", _CASES)
def test_pool_render_includes_all_items(name: str, builder):
    """render_for_prompt must include every item with its findings."""
    context = builder()
    items = [
        EvidencePoolItem.from_collector_tool(
            source_agent="passenger",
            tool_name="events_between",
            params={"start": _ts(8, 50), "end": _ts(9, 10)},
            findings=[ToolFinding(
                id="f1", tool="t", kind="fact",
                statement="Finding one.",
            )],
        ),
        EvidencePoolItem.from_collector_tool(
            source_agent="driver",
            tool_name="gps_at",
            params={"timestamp": _ts(9, 0)},
            findings=[ToolFinding(
                id="f2", tool="t", kind="fact",
                statement="Finding two.",
            )],
        ),
    ]
    text = EvidencePool.render_for_prompt([i.model_dump() for i in items])
    assert "passenger" in text
    assert "driver" in text
    assert "Finding one." in text
    assert "Finding two." in text


# ---------------------------------------------------------------------------
# Case-specific assertions
# ---------------------------------------------------------------------------

def test_case1_queries_include_gps_at():
    """Case 1 (no-show + GPS gap) should trigger gps_at queries."""
    context = _case1_no_show_gps_gap()
    planner = QueryPlanner(agent_name="passenger")
    plans = planner._plan(context)
    assert any(p.tool == "gps_at" for p in plans), "Expected gps_at for GPS gap case"


def test_case2_queries_include_events_between():
    """Case 2 (fare + surge) should trigger events_between for booking window."""
    context = _case2_fare_surge_route()
    planner = QueryPlanner(agent_name="passenger")
    plans = planner._plan(context)
    assert any(p.tool == "events_between" for p in plans), "Expected events_between for surge case"


def test_case3_queries_for_route_deviation():
    """Case 3 (route deviation) should trigger route-related queries."""
    context = _case3_route_deviation_closure()
    planner = QueryPlanner(agent_name="passenger")
    plans = planner._plan(context)
    # Route deviation may trigger events_between or gps_at
    assert len(plans) >= 1, "Expected at least one query for route deviation"


def test_case4_queries_for_safety():
    """Case 4 (service quality + safety) should trigger full-trip events."""
    context = _case4_service_quality_safety()
    planner = QueryPlanner(agent_name="passenger")
    plans = planner._plan(context)
    assert any(p.tool == "events_between" for p in plans), "Expected events_between for safety alerts"


def test_case5_queries_for_driver_delay():
    """Case 5 (cancellation + driver delay) should trigger proximity/location queries."""
    context = _case5_cancellation_driver_delay()
    planner = QueryPlanner(agent_name="passenger")
    plans = planner._plan(context)
    assert len(plans) >= 1, "Expected queries for driver delay case"
    assert any(p.tool in {"gps_at", "events_between"} for p in plans)
