"""
Query Planner: autonomous fact-finding for advocate agents.

Each agent calls the planner at the start of analyse().  The planner looks at
 the dispute type, the Collector's deterministic findings, and any gaps or
 conflicts, then decides which additional Collector tools (gps_at,
events_between, …) or policy topics should be run.

Rules:
- The planner is deterministic (no LLM, no tokens).
- It never invents data; if a timestamp is missing the query is skipped.
- Every query result is deposited into the shared evidence_pool on the
  DisputeContext so the other side and the Judge can see it.
- An agent may run at most MAX_AUTO_QUERIES queries to keep cost bounded.
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any

from src.agents.collector import CollectorAgent, DisputeContext
from src.agents.collector_tools import Finding
from src.core.evidence_pool import EvidencePoolItem

logger = logging.getLogger(__name__)

# Hard cap on auto-queries per agent per case
MAX_AUTO_QUERIES = 3

_SGT = timezone(timedelta(hours=8))


def _ts(value: str | None) -> datetime | None:
    if not value or not isinstance(value, str):
        return None
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=_SGT)


def _fmt(dt: datetime | None) -> str | None:
    return dt.isoformat() if dt else None


def _trip_time(context: DisputeContext) -> datetime | None:
    """Best guess at trip start time (scheduled or first event)."""
    trip = context.trip or {}
    t = _ts(trip.get("scheduled_time"))
    if t:
        return t
    events = context.app_events or []
    for e in events:
        t = _ts(e.get("timestamp"))
        if t:
            return t
    return None


def _cancellation_time(context: DisputeContext) -> datetime | None:
    return _ts((context.trip or {}).get("cancellation_time"))


def _arrival_time(context: DisputeContext) -> datetime | None:
    trip = context.trip or {}
    t = _ts(trip.get("driver_arrival_time"))
    if t:
        return t
    for e in context.app_events or []:
        if e.get("event_type") == "driver_arrived":
            t = _ts(e.get("timestamp"))
            if t:
                return t
    return None


def _pickup_window(context: DisputeContext) -> tuple[datetime | None, datetime | None]:
    """Return (window_start, window_end) around the scheduled pickup."""
    scheduled = _trip_time(context)
    if not scheduled:
        return None, None
    return scheduled - timedelta(minutes=10), scheduled + timedelta(minutes=10)


class QueryPlan:
    """One planned query."""

    def __init__(
        self,
        tool: str,
        params: dict[str, Any],
        reason: str,
    ):
        self.tool = tool
        self.params = params
        self.reason = reason

    def __repr__(self) -> str:
        return f"QueryPlan({self.tool}, {self.params}, {self.reason!r})"


class QueryPlanner:
    """Plans and executes autonomous queries for an advocate agent."""

    def __init__(self, agent_name: str, collector: CollectorAgent | None = None):
        self.agent_name = agent_name
        self._collector = collector or CollectorAgent()

    # ------------------------------------------------------------------ #
    # Public API
    # ------------------------------------------------------------------ #

    async def auto_query(self, context: DisputeContext) -> list[EvidencePoolItem]:
        """
        Run the planner and execute the resulting queries.

        Returns a list of EvidencePoolItem (already executed).
        The caller is responsible for appending them to context.evidence_pool.
        """
        plans = self._plan(context)
        if not plans:
            return []

        executed: list[EvidencePoolItem] = []
        for plan in plans[:MAX_AUTO_QUERIES]:
            findings = self._execute_plan(context, plan)
            if findings:
                executed.append(
                    EvidencePoolItem.from_collector_tool(
                        source_agent=self.agent_name,
                        tool_name=plan.tool,
                        params=plan.params,
                        findings=findings,
                    )
                )
        return executed

    # ------------------------------------------------------------------ #
    # Planning rules (deterministic, no LLM)
    # ------------------------------------------------------------------ #

    def _plan(self, context: DisputeContext) -> list[QueryPlan]:
        """Return ordered list of QueryPlan objects."""
        plans: list[QueryPlan] = []
        findings = context.findings or []
        dispute_type = getattr(context.type, "value", context.type) or ""

        # Helper to check if a finding id exists
        def has(*ids: str) -> bool:
            return any(f.id in ids for f in findings if hasattr(f, "id"))

        def has_dict(*ids: str) -> bool:
            return any((f.get("id") in ids if isinstance(f, dict) else False) for f in findings)

        # Use either model or dict findings
        finding_ids = set()
        for f in findings:
            if hasattr(f, "id"):
                finding_ids.add(f.id)
            elif isinstance(f, dict):
                finding_ids.add(f.get("id", ""))

        # ---------- Location-based disputes ----------
        if dispute_type in ("no_show", "cancellation_refund", "route_deviation"):
            # Arrival is contested: see what events happened around pickup
            if "consistency.arrival_without_event" in finding_ids \
                    or "consistency.no_show_without_arrival" in finding_ids:
                t0, t1 = _pickup_window(context)
                if t0 and t1:
                    plans.append(QueryPlan(
                        "events_between",
                        {"start": _fmt(t0), "end": _fmt(t1)},
                        "arrival record is contested; inspect events around pickup",
                    ))

            # GPS shows driver was far from pickup at cancellation
            if "pickup_proximity.at_cancellation" in finding_ids:
                cancel = _cancellation_time(context)
                if cancel:
                    plans.append(QueryPlan(
                        "gps_at",
                        {"timestamp": _fmt(cancel)},
                        "driver GPS at cancellation moment",
                    ))

            # No arrival recorded but we have scheduled time
            if "wait_time.no_arrival" in finding_ids:
                scheduled = _trip_time(context)
                if scheduled:
                    plans.append(QueryPlan(
                        "gps_at",
                        {"timestamp": _fmt(scheduled)},
                        "driver GPS at scheduled pickup (no arrival recorded)",
                    ))

            # GPS signal lost during critical period
            if "data_gaps.gps_signal_lost" in finding_ids:
                arrival = _arrival_time(context)
                if arrival:
                    plans.append(QueryPlan(
                        "gps_at",
                        {"timestamp": _fmt(arrival)},
                        "driver GPS at claimed arrival time (signal was lost)",
                    ))

            # Excessive wait time recorded: inspect events around the wait period
            if "wait_time.elapsed" in finding_ids:
                scheduled = _trip_time(context)
                cancel = _cancellation_time(context)
                if scheduled and cancel:
                    plans.append(QueryPlan(
                        "events_between",
                        {"start": _fmt(scheduled), "end": _fmt(cancel)},
                        "passenger waited an extended time; inspect all events from scheduled to cancellation",
                    ))

        # ---------- Route deviation ----------
        if dispute_type == "route_deviation":
            # Closure claimed but unverified: inspect events for official notices
            if "route_check.closure_unverified" in finding_ids:
                start = _trip_time(context)
                end = _ts((context.trip or {}).get("end_time"))
                if start and end:
                    plans.append(QueryPlan(
                        "events_between",
                        {"start": _fmt(start), "end": _fmt(end)},
                        "driver claims road closure but no official data; inspect trip events",
                    ))

            # High deviation: check GPS at route recalculation moment
            trip = context.trip or {}
            deviation = trip.get("route_deviation_percent")
            try:
                deviation_val = float(deviation) if deviation is not None else 0
            except (TypeError, ValueError):
                deviation_val = 0
            if deviation_val >= 30:
                start = _trip_time(context)
                if start:
                    t0 = start - timedelta(minutes=5)
                    t1 = start + timedelta(minutes=30)
                    plans.append(QueryPlan(
                        "events_between",
                        {"start": _fmt(t0), "end": _fmt(t1)},
                        f"route deviation {deviation_val}% is high; inspect events around trip",
                    ))

        # ---------- Fare disputes ----------
        if dispute_type == "fare_dispute":
            # Surge timing is unclear: look at events around booking
            if "fare_check.surge_timing" in finding_ids:
                scheduled = _trip_time(context)
                if scheduled:
                    t0 = scheduled - timedelta(minutes=30)
                    t1 = scheduled + timedelta(minutes=5)
                    plans.append(QueryPlan(
                        "events_between",
                        {"start": _fmt(t0), "end": _fmt(t1)},
                        "surge applied; inspect booking and acceptance events",
                    ))

        # ---------- Service quality / safety ----------
        if dispute_type == "service_quality":
            # Speeding or harsh braking alerts: look at the whole trip window
            if "speed_profile.max" in finding_ids:
                trip = context.trip or {}
                start = _ts(trip.get("start_time")) or _trip_time(context)
                end = _ts(trip.get("end_time"))
                if start and end:
                    plans.append(QueryPlan(
                        "events_between",
                        {"start": _fmt(start), "end": _fmt(end)},
                        "driving behaviour alerts; inspect full trip events",
                    ))

        # ---------- General: contact attempts gap ----------
        # If chat_log exists but contact_attempts shows zero messages from one side,
        # look at the events around pickup to see if calls were made via app_events
        if "contact_attempts.rider" in finding_ids or "contact_attempts.driver" in finding_ids:
            scheduled = _trip_time(context)
            if scheduled:
                t0 = scheduled - timedelta(minutes=15)
                t1 = _cancellation_time(context) or (scheduled + timedelta(minutes=30))
                plans.append(QueryPlan(
                    "events_between",
                    {"start": _fmt(t0), "end": _fmt(t1)},
                    "contact pattern unusual; inspect all events around trip",
                ))

        # Deduplicate by (tool, params)
        seen: set[tuple] = set()
        unique: list[QueryPlan] = []
        for p in plans:
            key = (p.tool, tuple(sorted(p.params.items())))
            if key not in seen:
                seen.add(key)
                unique.append(p)
        return unique

    # ------------------------------------------------------------------ #
    # Execution
    # ------------------------------------------------------------------ #

    def _execute_plan(self, context: DisputeContext, plan: QueryPlan) -> list[Finding]:
        try:
            return self._collector.query(context, plan.tool, **plan.params)
        except Exception as exc:
            logger.warning("Auto-query %s(%s) failed for %s: %s",
                           plan.tool, plan.params, self.agent_name, exc)
            return [Finding(
                id=f"auto_query.{plan.tool}.error",
                tool="query_planner",
                kind="gap",
                statement=f"Auto-query {plan.tool} failed: {exc}",
                value={"tool": plan.tool, "params": plan.params, "error": str(exc)},
            )]
