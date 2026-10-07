"""
Collector tools: deterministic fact-finding over a DisputeContext.

Every tool is plain Python (no LLM, no tokens). It reads the platform data the
Collector already gathered and returns Findings. A Finding states one fact,
conflict or gap and names exactly where it came from, e.g.
"gps_trace[3]" or "trip.cancellation_time", so the other agents can check it.

Rules:
- Tools only compute and compare. They never judge who is right or apply a
  policy threshold; that is the Policy / Arbitrator agents' job.
- Raw data is never changed.
- A tool with nothing to say returns [] (e.g. no fare data on a no-show case).

Two kinds of tools:
- STANDARD_TOOLS run on every case during collection.
- QUERY_TOOLS take arguments; other agents can call them later through
  CollectorAgent.query(...), e.g. "where was the driver at 09:08?".
"""

import math
from datetime import datetime, timedelta, timezone
from typing import Any, Callable, Literal

from pydantic import BaseModel

# Datasets are Singapore trips; a timestamp without an offset is read as SGT
_SGT = timezone(timedelta(hours=8))

# GPS statuses recorded before the rider is picked up
_PRE_PICKUP_STATUSES = {"en_route", "arrived", "waiting", "cancelled"}

# A driver_arrived event whose GPS is further than this from the pickup is
# flagged as a data conflict (not a verdict: the Policy agent decides what counts)
_ARRIVAL_GPS_MISMATCH_KM = 0.5

# events_between lists at most this many events in its statement (all are kept in value)
_MAX_LISTED_EVENTS = 15


class Finding(BaseModel):
    """One fact the Collector established, with where it came from."""
    id: str                                     # stable key, e.g. "pickup_proximity.nearest"
    tool: str                                   # tool that produced it
    kind: Literal["fact", "conflict", "gap"]    # conflict = two sources disagree; gap = data missing
    statement: str                              # one plain sentence
    value: dict[str, Any] = {}                  # the numbers behind the sentence
    sources: list[str] = []                     # e.g. ["gps_trace[3]", "trip.pickup_location"]


# ---------------------------------------------------------------------- #
# Helpers
# ---------------------------------------------------------------------- #

def _ts(value) -> datetime | None:
    """Parse an ISO timestamp; None if missing or unreadable."""
    if not value or not isinstance(value, str):
        return None
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=_SGT)


def _minutes(a: datetime, b: datetime) -> float:
    return round((b - a).total_seconds() / 60, 1)


def _hhmm(dt: datetime) -> str:
    return dt.astimezone(_SGT).strftime("%H:%M")


def _km(lat1, lng1, lat2, lng2) -> float:
    """Great-circle distance in km (haversine)."""
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = p2 - p1, math.radians(lng2 - lng1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return round(2 * 6371.0088 * math.asin(math.sqrt(a)), 2)


def _latlng(loc) -> tuple[float, float] | None:
    """Coordinates from a location dict (lat/lng or latitude/longitude)."""
    if not isinstance(loc, dict):
        return None
    lat = loc.get("lat", loc.get("latitude"))
    lng = loc.get("lng", loc.get("longitude"))
    if isinstance(lat, (int, float)) and isinstance(lng, (int, float)):
        return float(lat), float(lng)
    return None


def _pickup(ctx) -> tuple[float, float] | None:
    return _latlng((ctx.trip or {}).get("pickup_location"))


def _gps_points(ctx) -> list[tuple[int, dict]]:
    """(index, point) for GPS points that have coordinates."""
    return [(i, p) for i, p in enumerate(ctx.gps_trace or []) if _latlng(p)]


def _events(ctx, *types: str) -> list[tuple[int, dict]]:
    """(index, event) for app events of the given types, in file order."""
    return [(i, e) for i, e in enumerate(ctx.app_events or []) if e.get("event_type") in types]


def _money(x) -> str:
    return f"S${x:.2f}"


# ---------------------------------------------------------------------- #
# Standard tools (run on every case)
# ---------------------------------------------------------------------- #

def pickup_proximity(ctx) -> list[Finding]:
    """How close the driver's GPS ever got to the pickup point.
    Only pre-pickup points count; on a completed trip the GPS starts at the pickup anyway."""
    pickup = _pickup(ctx)
    points = [(i, p) for i, p in _gps_points(ctx) if p.get("status") in _PRE_PICKUP_STATUSES]
    if not pickup or not points:
        return []
    dists = [(i, p, _km(*pickup, *_latlng(p))) for i, p in points]
    i, p, d = min(dists, key=lambda x: x[2])
    out = [Finding(
        id="pickup_proximity.nearest", tool="pickup_proximity", kind="fact",
        statement=f"Driver GPS came within {d} km of the pickup at its closest "
                  f"({p.get('timestamp')}, status {p.get('status', 'unknown')}).",
        value={"nearest_km": d, "at": p.get("timestamp"), "status": p.get("status")},
        sources=[f"gps_trace[{i}]", "trip.pickup_location"],
    )]
    # Where the driver was when the trip was cancelled (no-show / cancellation cases)
    li, lp, ld = dists[-1]
    if lp.get("status") == "cancelled":
        out.append(Finding(
            id="pickup_proximity.at_cancellation", tool="pickup_proximity", kind="fact",
            statement=f"At cancellation ({lp.get('timestamp')}) the driver GPS was {ld} km from the pickup.",
            value={"distance_km": ld, "at": lp.get("timestamp")},
            sources=[f"gps_trace[{li}]", "trip.pickup_location"],
        ))
    return out


def wait_time(ctx) -> list[Finding]:
    """Arrival vs scheduled time, and how long the driver waited before cancelling."""
    trip = ctx.trip or {}
    arrival, arrival_src = _ts(trip.get("driver_arrival_time")), "trip.driver_arrival_time"
    if not arrival:
        arrived = _events(ctx, "driver_arrived")
        if arrived:
            arrival = _ts(arrived[0][1].get("timestamp"))
            arrival_src = f"app_events[{arrived[0][0]}]"
    scheduled = _ts(trip.get("scheduled_time"))
    cancelled = _ts(trip.get("cancellation_time"))
    out = []
    if arrival and scheduled:
        late = _minutes(scheduled, arrival)
        out.append(Finding(
            id="wait_time.arrival_vs_scheduled", tool="wait_time", kind="fact",
            statement=(f"Driver arrived {abs(late)} min {'after' if late > 0 else 'before'} the scheduled pickup"
                       if late else "Driver arrived exactly at the scheduled pickup time")
                      + f" ({_hhmm(arrival)} vs {_hhmm(scheduled)}).",
            value={"minutes_late": late, "arrived_at": arrival.isoformat(), "scheduled": scheduled.isoformat()},
            sources=[arrival_src, "trip.scheduled_time"],
        ))
    if arrival and cancelled:
        waited = _minutes(arrival, cancelled)
        out.append(Finding(
            id="wait_time.waited_before_cancel", tool="wait_time", kind="fact",
            statement=f"Driver waited {waited} min between arriving ({_hhmm(arrival)}) "
                      f"and cancelling ({_hhmm(cancelled)}).",
            value={"minutes_waited": waited},
            sources=[arrival_src, "trip.cancellation_time"],
        ))
    elif cancelled and scheduled and not arrival:
        m = _minutes(scheduled, cancelled)
        out.append(Finding(
            id="wait_time.no_arrival", tool="wait_time", kind="fact",
            statement=f"No driver arrival is recorded; the trip was cancelled at {_hhmm(cancelled)}, "
                      f"{abs(m)} min {'after' if m >= 0 else 'before'} the scheduled pickup ({_hhmm(scheduled)}).",
            value={"minutes_after_scheduled": m},
            sources=["trip.driver_arrival_time", "app_events", "trip.cancellation_time"],
        ))
    return out


def contact_attempts(ctx) -> list[Finding]:
    """Who tried to reach whom: messages and calls per sender."""
    counts: dict[str, dict] = {}
    for i, m in enumerate(ctx.chat_log or []):
        sender = m.get("sender")
        if sender not in ("rider", "driver"):
            continue
        c = counts.setdefault(sender, {"messages": 0, "calls": 0, "sources": []})
        c["calls" if m.get("message_type") == "call" else "messages"] += 1
        c["sources"].append(f"chat_log[{i}]")
    for i, e in _events(ctx, "rider_called_driver", "driver_called_rider"):
        sender = "rider" if e["event_type"].startswith("rider") else "driver"
        c = counts.setdefault(sender, {"messages": 0, "calls": 0, "sources": []})
        c["sources"].append(f"app_events[{i}]")
    out = []
    for sender in ("rider", "driver"):
        c = counts.get(sender)
        if c is None:
            out.append(Finding(
                id=f"contact_attempts.{sender}", tool="contact_attempts", kind="fact",
                statement=f"The {sender} sent no messages and made no calls in the chat log.",
                value={"messages": 0, "calls": 0}, sources=["chat_log"],
            ))
            continue
        out.append(Finding(
            id=f"contact_attempts.{sender}", tool="contact_attempts", kind="fact",
            statement=f"The {sender} sent {c['messages']} message(s) and made {c['calls']} call(s).",
            value={"messages": c["messages"], "calls": c["calls"]}, sources=c["sources"],
        ))
    return out if ctx.chat_log else []


def fare_check(ctx) -> list[Finding]:
    """Quoted vs charged fare, and whether the fare breakdown adds up."""
    trip = ctx.trip or {}
    est, total = trip.get("estimated_fare"), trip.get("total_fare")
    out = []
    if isinstance(est, (int, float)) and isinstance(total, (int, float)) and est:
        diff = round(total - est, 2)
        out.append(Finding(
            id="fare_check.quoted_vs_charged", tool="fare_check", kind="fact",
            statement=f"Charged {_money(total)} vs estimated {_money(est)}: "
                      f"{'+' if diff >= 0 else '-'}{_money(abs(diff))} ({round(diff / est * 100, 1)}%).",
            value={"estimated": est, "charged": total, "difference": diff,
                   "difference_percent": round(diff / est * 100, 1)},
            sources=["trip.estimated_fare", "trip.total_fare"],
        ))
    fb = trip.get("fare_breakdown")
    if isinstance(fb, dict):
        parts = [fb.get(k) for k in ("base_fare", "distance_fare", "time_fare")]
        if all(isinstance(x, (int, float)) for x in parts) and isinstance(fb.get("subtotal"), (int, float)):
            s = round(sum(parts), 2)
            if abs(s - fb["subtotal"]) > 0.01:
                out.append(Finding(
                    id="fare_check.subtotal_mismatch", tool="fare_check", kind="conflict",
                    statement=f"Fare components add up to {_money(s)} but the subtotal says {_money(fb['subtotal'])}.",
                    value={"components_sum": s, "subtotal": fb["subtotal"]},
                    sources=["trip.fare_breakdown"],
                ))
        if isinstance(fb.get("total"), (int, float)) and isinstance(total, (int, float)) \
                and abs(fb["total"] - total) > 0.01:
            out.append(Finding(
                id="fare_check.total_mismatch", tool="fare_check", kind="conflict",
                statement=f"Fare breakdown total {_money(fb['total'])} differs from the charged fare {_money(total)}.",
                value={"breakdown_total": fb["total"], "charged": total},
                sources=["trip.fare_breakdown.total", "trip.total_fare"],
            ))
        surge = fb.get("surge_multiplier")
        if isinstance(surge, (int, float)) and surge > 1:
            out.extend(_surge_timing(ctx, surge))
    return out


def _surge_timing(ctx, surge: float) -> list[Finding]:
    """Was the surge shown / accepted before the booking was confirmed?"""
    booked = _events(ctx, "booking_confirmed")
    booked_at = _ts(booked[0][1].get("timestamp")) if booked else None
    rows = []
    for i, e in _events(ctx, "fare_quote_shown", "rider_accepted_surge", "surge_multiplier_changed"):
        at = _ts(e.get("timestamp"))
        when = ("before" if at < booked_at else "after") if at and booked_at else "unknown time vs"
        rows.append((i, e["event_type"], when))
    value = {"surge_multiplier": surge, "events": [{"event": t, "relative_to_booking": w} for _, t, w in rows]}
    text = "; ".join(f"{t} {w} booking" for _, t, w in rows) or "no surge-related app event recorded"
    return [Finding(
        id="fare_check.surge_timing", tool="fare_check", kind="fact",
        statement=f"Surge x{surge} applied. Surge events: {text}.",
        value=value,
        sources=["trip.fare_breakdown.surge_multiplier"] + [f"app_events[{i}]" for i, _, _ in rows]
                + ([f"app_events[{booked[0][0]}]"] if booked else []),
    )]


def route_check(ctx) -> list[Finding]:
    """Estimated vs actual distance and duration; checks the reported deviation %."""
    trip = ctx.trip or {}
    est, act = trip.get("estimated_distance_km"), trip.get("actual_distance_km")
    if not (isinstance(est, (int, float)) and isinstance(act, (int, float)) and est):
        return []
    pct = round((act - est) / est * 100, 1)
    out = [Finding(
        id="route_check.distance", tool="route_check", kind="fact",
        statement=f"Actual distance {act} km vs estimated {est} km ({'+' if pct >= 0 else ''}{pct}%).",
        value={"estimated_km": est, "actual_km": act, "deviation_percent": pct},
        sources=["trip.estimated_distance_km", "trip.actual_distance_km"],
    )]
    est_min, act_min = trip.get("estimated_duration_min"), trip.get("actual_duration_min")
    if isinstance(est_min, (int, float)) and isinstance(act_min, (int, float)):
        out.append(Finding(
            id="route_check.duration", tool="route_check", kind="fact",
            statement=f"Actual duration {act_min} min vs estimated {est_min} min "
                      f"({'+' if act_min >= est_min else ''}{round(act_min - est_min, 1)} min).",
            value={"estimated_min": est_min, "actual_min": act_min},
            sources=["trip.estimated_duration_min", "trip.actual_duration_min"],
        ))
    reported = trip.get("route_deviation_percent")
    if isinstance(reported, (int, float)) and abs(reported - pct) > 1:
        out.append(Finding(
            id="route_check.reported_deviation_mismatch", tool="route_check", kind="conflict",
            statement=f"Platform reports {reported}% route deviation but the distances give {pct}%.",
            value={"reported_percent": reported, "computed_percent": pct},
            sources=["trip.route_deviation_percent", "trip.estimated_distance_km", "trip.actual_distance_km"],
        ))
    return out


def speed_profile(ctx) -> list[Finding]:
    """Top recorded speed and any driving-behaviour alerts."""
    speeds = [(i, p) for i, p in enumerate(ctx.gps_trace or []) if isinstance(p.get("speed_kmh"), (int, float))]
    alerts = _events(ctx, "speeding_alert", "harsh_braking_detected")
    if not speeds or not any(p.get("status") == "on_trip" for _, p in speeds):
        return []
    i, p = max(speeds, key=lambda x: x[1]["speed_kmh"])
    kinds = sorted({e["event_type"] for _, e in alerts})
    return [Finding(
        id="speed_profile.max", tool="speed_profile", kind="fact",
        statement=f"Top recorded speed {p['speed_kmh']} km/h at {p.get('timestamp')}; "
                  + (f"{len(alerts)} driving alert(s): {', '.join(kinds)}." if alerts else "no driving alerts recorded."),
        value={"max_speed_kmh": p["speed_kmh"], "at": p.get("timestamp"), "alerts": len(alerts)},
        sources=[f"gps_trace[{i}]"] + [f"app_events[{j}]" for j, _ in alerts],
    )]


def fee_check(ctx) -> list[Finding]:
    """The cancellation fee charged vs the fee in the trip's policy parameters."""
    fee = (ctx.trip or {}).get("cancellation_fee")
    policy_fee = (ctx.platform_policy or {}).get("cancellation_fee_after_wait")
    if not isinstance(fee, (int, float)):
        return []
    out = [Finding(
        id="fee_check.charged", tool="fee_check", kind="fact",
        statement=f"A {_money(fee)} cancellation fee was charged"
                  + (f" (reason recorded: {ctx.trip.get('cancellation_reason')})." if ctx.trip.get("cancellation_reason") else "."),
        value={"fee": fee, "reason": ctx.trip.get("cancellation_reason")},
        sources=["trip.cancellation_fee", "trip.cancellation_reason"],
    )]
    if isinstance(policy_fee, (int, float)) and abs(policy_fee - fee) > 0.01:
        out.append(Finding(
            id="fee_check.policy_amount_mismatch", tool="fee_check", kind="conflict",
            statement=f"Fee charged ({_money(fee)}) differs from the trip's policy fee ({_money(policy_fee)}).",
            value={"charged": fee, "policy_fee": policy_fee},
            sources=["trip.cancellation_fee", "platform_policy.cancellation_fee_after_wait"],
        ))
    return out


def consistency_check(ctx) -> list[Finding]:
    """Cross-check sources that should agree: trip record, app events, GPS."""
    trip = ctx.trip or {}
    out = []
    arrived = _events(ctx, "driver_arrived")
    trip_arrival = _ts(trip.get("driver_arrival_time"))

    # 1. Trip record vs app event log on driver arrival
    if trip_arrival and not arrived and ctx.app_events:
        out.append(Finding(
            id="consistency.arrival_without_event", tool="consistency_check", kind="conflict",
            statement=f"Trip record has an arrival time ({_hhmm(trip_arrival)}) but the app log has no driver_arrived event.",
            value={"trip_arrival": trip.get("driver_arrival_time")},
            sources=["trip.driver_arrival_time", "app_events"],
        ))

    # 2. Cancelled as rider no-show, but no arrival recorded anywhere
    if trip.get("cancellation_reason") == "rider_no_show" and not trip_arrival and not arrived:
        out.append(Finding(
            id="consistency.no_show_without_arrival", tool="consistency_check", kind="conflict",
            statement="Trip was cancelled as a rider no-show, but no driver arrival is recorded "
                      "(no driver_arrival_time and no driver_arrived event).",
            value={"cancellation_reason": "rider_no_show"},
            sources=["trip.cancellation_reason", "trip.driver_arrival_time", "app_events"],
        ))

    # 3. Arrival event vs where the GPS actually was at that moment
    pickup, points = _pickup(ctx), _gps_points(ctx)
    if arrived and pickup and points:
        at = _ts(arrived[0][1].get("timestamp"))
        if at:
            i, p = min(points, key=lambda x: abs(((_ts(x[1].get("timestamp")) or at) - at).total_seconds()))
            d = _km(*pickup, *_latlng(p))
            if d > _ARRIVAL_GPS_MISMATCH_KM:
                out.append(Finding(
                    id="consistency.arrival_gps_far", tool="consistency_check", kind="conflict",
                    statement=f"driver_arrived was logged at {_hhmm(at)} but the nearest-in-time GPS point "
                              f"({p.get('timestamp')}) is {d} km from the pickup.",
                    value={"distance_km": d, "gps_at": p.get("timestamp")},
                    sources=[f"app_events[{arrived[0][0]}]", f"gps_trace[{i}]", "trip.pickup_location"],
                ))
    return out


def data_gaps(ctx) -> list[Finding]:
    """Data that is missing or unverifiable."""
    out = []
    missing = [f for f in (ctx.data_completeness or {}).get("missing", []) if f != "payment"]
    if missing:
        out.append(Finding(
            id="data_gaps.missing_sources", tool="data_gaps", kind="gap",
            statement=f"Missing platform data: {', '.join(missing)}.",
            value={"missing": missing}, sources=["data_completeness"],
        ))
    for i, e in _events(ctx, "gps_signal_lost"):
        out.append(Finding(
            id="data_gaps.gps_signal_lost", tool="data_gaps", kind="gap",
            statement=f"Driver GPS stopped reporting at {e.get('timestamp')}; "
                      "location after that point cannot be verified.",
            value={"at": e.get("timestamp")}, sources=[f"app_events[{i}]"],
        ))
    return out


# ---------------------------------------------------------------------- #
# Query tools (called on demand with arguments)
# ---------------------------------------------------------------------- #

def gps_at(ctx, timestamp: str) -> list[Finding]:
    """Where the driver was at (or nearest to) a given time."""
    at, points = _ts(timestamp), _gps_points(ctx)
    if not at:
        return [Finding(id="gps_at.bad_time", tool="gps_at", kind="gap",
                        statement=f"Could not read the time '{timestamp}'.", value={"timestamp": timestamp})]
    if not points:
        return [Finding(id="gps_at.no_gps", tool="gps_at", kind="gap",
                        statement="No GPS data is available for this trip.", sources=["gps_trace"])]
    i, p = min(points, key=lambda x: abs(((_ts(x[1].get("timestamp")) or at) - at).total_seconds()))
    pickup = _pickup(ctx)
    d = _km(*pickup, *_latlng(p)) if pickup else None
    return [Finding(
        id="gps_at.result", tool="gps_at", kind="fact",
        statement=f"Nearest GPS point to {timestamp} is {p.get('timestamp')}: status {p.get('status', 'unknown')}, "
                  f"speed {p.get('speed_kmh', '?')} km/h" + (f", {d} km from the pickup." if d is not None else "."),
        value={"gps_timestamp": p.get("timestamp"), "status": p.get("status"),
               "speed_kmh": p.get("speed_kmh"), "distance_to_pickup_km": d},
        sources=[f"gps_trace[{i}]"] + (["trip.pickup_location"] if pickup else []),
    )]


def events_between(ctx, start: str, end: str) -> list[Finding]:
    """All app events and chat messages between two times."""
    t0, t1 = _ts(start), _ts(end)
    if not t0 or not t1:
        return [Finding(id="events_between.bad_time", tool="events_between", kind="gap",
                        statement=f"Could not read the time range '{start}' to '{end}'.")]
    rows = []
    for i, e in enumerate(ctx.app_events or []):
        at = _ts(e.get("timestamp"))
        if at and t0 <= at <= t1:
            rows.append((at, f"app_events[{i}]", f"{e.get('event_type')}: {e.get('details', '')}"))
    for i, m in enumerate(ctx.chat_log or []):
        at = _ts(m.get("timestamp"))
        if at and t0 <= at <= t1:
            rows.append((at, f"chat_log[{i}]", f"{m.get('sender')} ({m.get('message_type')}): {m.get('message', '')}"))
    rows.sort(key=lambda r: r[0])
    # The statement carries the events themselves: a bare count gives an agent nothing to argue from
    listed = "; ".join(f"{r[0].strftime('%H:%M:%S')} {r[2]} ({r[1]})" for r in rows[:_MAX_LISTED_EVENTS])
    more = f"; and {len(rows) - _MAX_LISTED_EVENTS} more" if len(rows) > _MAX_LISTED_EVENTS else ""
    return [Finding(
        id="events_between.result", tool="events_between", kind="fact",
        statement=f"{len(rows)} event(s) between {start} and {end}" + (f": {listed}{more}." if rows else "."),
        value={"events": [{"at": r[0].isoformat(), "source": r[1], "text": r[2]} for r in rows]},
        sources=[r[1] for r in rows],
    )]


# ---------------------------------------------------------------------- #
# Registry
# ---------------------------------------------------------------------- #

STANDARD_TOOLS: dict[str, Callable] = {
    "pickup_proximity": pickup_proximity,
    "wait_time": wait_time,
    "contact_attempts": contact_attempts,
    "fare_check": fare_check,
    "route_check": route_check,
    "speed_profile": speed_profile,
    "fee_check": fee_check,
    "consistency_check": consistency_check,
    "data_gaps": data_gaps,
}

QUERY_TOOLS: dict[str, Callable] = {
    "gps_at": gps_at,
    "events_between": events_between,
}
