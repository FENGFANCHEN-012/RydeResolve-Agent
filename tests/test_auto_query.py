"""
Tests for the autonomous query system (QueryPlanner + EvidencePool).

All tests use mocks; no API keys or running services are required.
"""
import json
import sys
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest

sys.path.insert(0, ".")

from src.agents.collector import DisputeContext, DisputeType, Finding
from src.agents.collector_tools import QUERY_TOOLS
from src.agents.passenger import PassengerAgent
from src.agents.driver import DriverAgent
from src.agents.query_planner import QueryPlanner
from src.core.evidence_pool import EvidencePool, EvidencePoolItem


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def make_context_no_show_with_conflict(**overrides) -> DisputeContext:
    """A no-show case where the arrival record is contested."""
    defaults = dict(
        dispute_id="TEST-NS-001",
        type=DisputeType.NO_SHOW,
        reporter="passenger",
        order_id="RYDE-NS-001",
        description="Driver never arrived, but I was charged a cancellation fee.",
        trip={
            "scheduled_time": "2026-09-21T09:00:00+08:00",
            "cancellation_time": "2026-09-21T09:08:00+08:00",
            "cancellation_reason": "rider_no_show",
            "cancellation_fee": 3.50,
            "pickup_location": {"lat": 1.2975, "lng": 103.8535},
        },
        app_events=[
            {"timestamp": "2026-09-21T08:55:00+08:00", "event_type": "booking_confirmed"},
        ],
        gps_trace=[
            {"timestamp": "2026-09-21T08:59:00+08:00", "lat": 1.2900, "lng": 103.8600, "status": "en_route"},
            {"timestamp": "2026-09-21T09:05:00+08:00", "lat": 1.2900, "lng": 103.8600, "status": "cancelled"},
        ],
        findings=[
            Finding(
                id="consistency.no_show_without_arrival",
                tool="consistency_check",
                kind="conflict",
                statement="Trip was cancelled as a rider no-show, but no driver arrival is recorded.",
                sources=["trip.cancellation_reason", "trip.driver_arrival_time", "app_events"],
            ),
            Finding(
                id="pickup_proximity.nearest",
                tool="pickup_proximity",
                kind="fact",
                statement="Driver GPS came within 0.85 km of the pickup at its closest.",
                value={"nearest_km": 0.85},
                sources=["gps_trace[0]", "trip.pickup_location"],
            ),
        ],
    )
    defaults.update(overrides)
    return DisputeContext(**defaults)


def make_context_fare_with_surge(**overrides) -> DisputeContext:
    """A fare dispute where surge timing may be unclear."""
    defaults = dict(
        dispute_id="TEST-FD-001",
        type=DisputeType.FARE,
        reporter="passenger",
        order_id="RYDE-FD-001",
        description="I was charged surge pricing but I didn't agree to it.",
        trip={
            "scheduled_time": "2026-09-21T18:00:00+08:00",
            "estimated_fare": 12.0,
            "total_fare": 18.0,
            "fare_breakdown": {"surge_multiplier": 1.5, "subtotal": 18.0, "total": 18.0},
        },
        app_events=[
            {"timestamp": "2026-09-21T17:55:00+08:00", "event_type": "booking_confirmed"},
            {"timestamp": "2026-09-21T17:56:00+08:00", "event_type": "fare_quote_shown"},
            {"timestamp": "2026-09-21T17:57:00+08:00", "event_type": "rider_accepted_surge"},
        ],
        findings=[
            Finding(
                id="fare_check.surge_timing",
                tool="fare_check",
                kind="fact",
                statement="Surge x1.5 applied. Surge events: fare_quote_shown before booking; rider_accepted_surge before booking.",
                sources=["trip.fare_breakdown.surge_multiplier", "app_events[1]", "app_events[2]"],
            ),
        ],
    )
    defaults.update(overrides)
    return DisputeContext(**defaults)


def make_mock_retriever(clauses: list[dict] | None = None) -> MagicMock:
    retriever = MagicMock()
    retriever.retrieve_for_dispute.return_value = clauses or []
    return retriever


def make_mock_llm_json(response_text: str = "{}") -> AsyncMock:
    llm = AsyncMock()
    llm.chat_json = AsyncMock(return_value=response_text)
    return llm


# ---------------------------------------------------------------------------
# 1. QueryPlanner plans the right queries for a no-show conflict
# ---------------------------------------------------------------------------

def test_planner_no_show_conflict():
    context = make_context_no_show_with_conflict()
    planner = QueryPlanner(agent_name="passenger")
    plans = planner._plan(context)

    # Should plan at least one query because of the no-show-without-arrival conflict
    assert len(plans) >= 1
    tool_names = {p.tool for p in plans}
    assert "events_between" in tool_names or "gps_at" in tool_names


# ---------------------------------------------------------------------------
# 2. QueryPlanner plans queries for fare dispute with surge
# ---------------------------------------------------------------------------

def test_planner_fare_surge():
    context = make_context_fare_with_surge()
    planner = QueryPlanner(agent_name="passenger")
    plans = planner._plan(context)

    # Should plan events_between because of surge timing
    assert any(p.tool == "events_between" for p in plans)


# ---------------------------------------------------------------------------
# 3. QueryPlanner deduplicates identical queries
# ---------------------------------------------------------------------------

def test_planner_deduplicates():
    # Create a context that would trigger the same query twice
    context = make_context_no_show_with_conflict(
        findings=[
            Finding(
                id="consistency.no_show_without_arrival",
                tool="consistency_check",
                kind="conflict",
                statement="No arrival.",
                sources=[],
            ),
            Finding(
                id="wait_time.no_arrival",
                tool="wait_time",
                kind="fact",
                statement="No driver arrival recorded.",
                sources=[],
            ),
        ],
    )
    planner = QueryPlanner(agent_name="passenger")
    plans = planner._plan(context)

    # Both findings could trigger a gps_at query, but they should be deduplicated
    gps_at_plans = [p for p in plans if p.tool == "gps_at"]
    assert len(gps_at_plans) <= 1


# ---------------------------------------------------------------------------
# 4. EvidencePoolItem serialises correctly
# ---------------------------------------------------------------------------

def test_evidence_pool_item_serialization():
    finding = Finding(
        id="test.fact",
        tool="test_tool",
        kind="fact",
        statement="Test statement.",
    )
    item = EvidencePoolItem.from_collector_tool(
        source_agent="passenger",
        tool_name="gps_at",
        params={"timestamp": "2026-09-21T09:00:00+08:00"},
        findings=[finding],
    )

    dumped = item.model_dump()
    assert dumped["source_agent"] == "passenger"
    assert dumped["item_type"] == "collector_tool"
    assert dumped["query"]["tool"] == "gps_at"
    assert len(dumped["findings"]) == 1
    assert dumped["findings"][0]["statement"] == "Test statement."


# ---------------------------------------------------------------------------
# 5. EvidencePool renders non-empty pool
# ---------------------------------------------------------------------------

def test_evidence_pool_render():
    item = EvidencePoolItem.from_collector_tool(
        source_agent="passenger",
        tool_name="gps_at",
        params={"timestamp": "2026-09-21T09:00:00+08:00"},
        findings=[Finding(
            id="test.fact", tool="test", kind="fact",
            statement="Driver was 0.5 km from pickup.",
        )],
    )
    text = EvidencePool.render_for_prompt([item])
    assert "SHARED EVIDENCE POOL" in text
    assert "passenger" in text
    assert "0.5 km" in text


# ---------------------------------------------------------------------------
# 6. EvidencePool merge deduplicates by item_id
# ---------------------------------------------------------------------------

def test_evidence_pool_merge():
    item1 = EvidencePoolItem.from_collector_tool(
        source_agent="passenger", tool_name="gps_at",
        params={"timestamp": "2026-09-21T09:00:00+08:00"},
        findings=[],
    )
    item2 = EvidencePoolItem.from_collector_tool(
        source_agent="driver", tool_name="gps_at",
        params={"timestamp": "2026-09-21T09:00:00+08:00"},
        findings=[],
    )
    merged = EvidencePool.merge_pools([item1.model_dump()], [item2])
    assert len(merged) == 2

    # Merging again should not duplicate
    merged2 = EvidencePool.merge_pools(merged, [item1])
    assert len(merged2) == 2


# ---------------------------------------------------------------------------
# 7. PassengerAgent analyze deposits into evidence_pool
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_passenger_agent_auto_query_deposits_to_pool():
    llm_response = json.dumps({
        "stance": "s", "evidence": [], "contradictory_evidence": [],
        "missing_evidence": [], "obligations": [], "remedy_requested": "",
        "policy_references": [], "reasoning": "r", "confidence": 0.5,
        "requires_human_review": False,
    })
    retriever = make_mock_retriever([])
    llm = make_mock_llm_json(llm_response)
    agent = PassengerAgent(llm_client=llm, retriever=retriever)

    context = make_context_no_show_with_conflict()
    assert context.evidence_pool == []

    await agent.analyze(context)

    # The agent should have deposited auto-query results into the pool
    assert len(context.evidence_pool) >= 1
    for item in context.evidence_pool:
        assert item["source_agent"] == "passenger"
        assert "item_id" in item


# ---------------------------------------------------------------------------
# 8. DriverAgent can see passenger's pool items in its prompt
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_driver_agent_sees_passenger_pool_items():
    llm_response = json.dumps({
        "stance": "s", "evidence": [], "contradictory_evidence": [],
        "missing_evidence": [], "obligations": [], "remedy_requested": "",
        "policy_references": [], "reasoning": "r", "confidence": 0.5,
        "requires_human_review": False,
    })
    sample_clauses = [
        {"clause": "Test clause", "source": "test.md", "section": "Test", "chunk_index": 0},
    ]
    retriever = make_mock_retriever(sample_clauses)
    llm = make_mock_llm_json(llm_response)
    driver_agent = DriverAgent(llm_client=llm, retriever=retriever)

    # Pre-populate the context with a passenger query result
    context = make_context_no_show_with_conflict()
    context.evidence_pool = [
        EvidencePoolItem.from_collector_tool(
            source_agent="passenger",
            tool_name="events_between",
            params={"start": "2026-09-21T08:50:00+08:00", "end": "2026-09-21T09:10:00+08:00"},
            findings=[Finding(
                id="test.fact", tool="test", kind="fact",
                statement="Passenger found no driver_arrived event.",
            )],
        ).model_dump(),
    ]

    await driver_agent.analyze(context)

    # The driver agent should also deposit its own queries
    assert len(context.evidence_pool) >= 2  # passenger's + driver's

    # Verify the prompt sent to the LLM contains the passenger's pool item
    call_args = llm.chat_json.call_args
    messages = call_args.kwargs.get("messages", [])
    user_msg = ""
    for m in messages:
        if m["role"] == "user":
            user_msg = m["content"]
            break

    assert "SHARED EVIDENCE POOL" in user_msg
    assert "passenger" in user_msg
    assert "Passenger found no driver_arrived event." in user_msg


# ---------------------------------------------------------------------------
# 9. Auto-query is skipped when there are no relevant findings
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_auto_query_skipped_for_clean_case():
    llm_response = json.dumps({
        "stance": "s", "evidence": [], "contradictory_evidence": [],
        "missing_evidence": [], "obligations": [], "remedy_requested": "",
        "policy_references": [], "reasoning": "r", "confidence": 0.5,
        "requires_human_review": False,
    })
    retriever = make_mock_retriever([])
    llm = make_mock_llm_json(llm_response)
    agent = PassengerAgent(llm_client=llm, retriever=retriever)

    # A simple route deviation with no conflicts or gaps
    context = DisputeContext(
        dispute_id="TEST-RD-001",
        type=DisputeType.ROUTE_DEVIATION,
        reporter="passenger",
        order_id="RYDE-RD-001",
        description="Driver took a longer route.",
        trip={"estimated_distance_km": 8.0, "actual_distance_km": 10.0},
        findings=[
            Finding(
                id="route_check.distance",
                tool="route_check",
                kind="fact",
                statement="Actual distance 10 km vs estimated 8 km (+25%).",
                sources=["trip.estimated_distance_km", "trip.actual_distance_km"],
            ),
        ],
    )

    await agent.analyze(context)

    # No auto-queries should have been triggered for a clean route-deviation case
    # (the finding is a plain fact, not a conflict or gap)
    # The pool may still be empty or only contain the passenger's own queries
    # (route deviation doesn't trigger any plans in the current rule set)
    driver_queries = [i for i in context.evidence_pool if i.get("source_agent") == "passenger"]
    assert len(driver_queries) == 0
