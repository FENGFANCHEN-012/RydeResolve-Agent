"""
Policy topics: a fixed catalogue used to fetch clauses the complaint may not mention (D14).

A complaint is often one sentence ("I was overcharged"), so a search with it can miss rules the
case turns on. The base clauses for a case therefore come from three places:
  1. the complaint search (ranked by section tags),
  2. the core topics of the classified dispute type (TYPE_TOPICS),
  3. topics triggered by the platform data (a cancellation fee was charged, surge was applied,
     a route-deviation alert fired, ...), see triggered_topics().
Advocates can also ask for topics from the same catalogue (policy_requests). A topic is a fixed
search: official help-centre wording plus the section tags it may come from, so nobody writes
free-text search terms and no LLM is involved.
"""

# name -> (search words in official wording, section tags the clause must carry)
TOPICS: dict[str, tuple[str, tuple[str, ...]]] = {
    "refund": ("refund request fee waiver request refund at Ryde's discretion",
               ("cancellation_refund", "fare_dispute", "general")),
    "cancellation_fee": ("cancellation fee grace period 3 minutes of matching will I be charged for cancelling",
                         ("cancellation_refund", "no_show")),
    "waiting_fee": ("waiting time fee I'm Here free waiting time driver waits", ("no_show",)),
    "no_show": ("rider no show driver waits cancellation fee no-show conditions", ("no_show",)),
    "fixed_fare": ("understanding the fare structure fixed fare by pick-up and drop-off points how are trip fares calculated",
                   ("fare_dispute", "route_deviation")),
    "fare_surge": ("surge peak pricing fare shown before booking upfront fare", ("fare_dispute",)),
    "transaction_fee": ("how is the payment transaction fee calculated booking fee", ("fare_dispute",)),
    "erp_toll": ("ERP toll charges added to the trip fare", ("fare_dispute",)),
    "route_detour": ("fixed fare by pick-up and drop-off points route suggested by the rider detour",
                     ("route_deviation",)),
    "cleaning_fee": ("rider made a mess cleaning fee claim receipt photo", ("driver_rights",)),
    "lost_item": ("lost item left in the vehicle", ("service_quality",)),
    "accident_insurance": ("accident insurance coverage who bears the financial costs", ("accident_liability",)),
    "safety_conduct": ("report a safety issue code of conduct unsafe driving speeding",
                       ("service_quality", "accident_liability")),
    "appeal": ("appeal dispute resolution complaints penalties", ("driver_rights", "general")),
    "delivery": ("RydeSEND delivery items damaged or lost delivery fee", ("delivery_dispute",)),
}

# Topics every case of a type needs, whatever the complaint says
TYPE_TOPICS: dict[str, tuple[str, ...]] = {
    "no_show": ("no_show", "waiting_fee", "cancellation_fee"),
    "cancellation_refund": ("cancellation_fee", "refund"),
    "fare_dispute": ("fixed_fare", "transaction_fee", "refund"),
    "route_deviation": ("fixed_fare", "route_detour", "refund"),
    "service_quality": ("safety_conduct",),
    "delivery_dispute": ("delivery",),
    "driver_rights": ("appeal",),
    "accident_liability": ("accident_insurance",),
}


def _get(obj, key):
    return obj.get(key) if isinstance(obj, dict) else getattr(obj, key, None)


def _positive(value) -> bool:
    try:
        return float(value) > 0
    except (TypeError, ValueError):
        return False


def triggered_topics(context) -> dict[str, str]:
    """Topics the platform data calls for, each with the plain reason (shown in the brief).
    Reads only platform records, never the complaint, so wording cannot trigger a topic."""
    trip = _get(context, "trip") or {}
    events = {e.get("event_type") for e in (_get(context, "app_events") or []) if isinstance(e, dict)}
    breakdown = " ".join(str(k).lower() for k in (trip.get("fare_breakdown") or {}))
    out: dict[str, str] = {}

    def add(topic, reason):
        out.setdefault(topic, reason)

    if _positive(trip.get("cancellation_fee")) or "cancellation_fee_applied" in events:
        add("cancellation_fee", "a cancellation fee was charged")
        add("refund", "a fee was charged that may be refunded")
    if "no_show" in str(trip.get("cancellation_reason") or "").lower():
        add("no_show", "the trip was cancelled as a rider no-show")
        add("waiting_fee", "the trip was cancelled as a rider no-show")
    if events & {"wait_timer_started", "wait_timer_expired"}:
        add("waiting_fee", "a waiting timer ran")
    if events & {"surge_multiplier_changed", "rider_accepted_surge"} or "surge" in breakdown:
        add("fare_surge", "surge pricing was applied")
    if "erp" in breakdown or "toll" in breakdown:
        add("erp_toll", "ERP or toll charges are in the fare")
    if events & {"route_deviation_alert", "route_recalculated", "traffic_incident_alert"} \
            or (_positive(trip.get("route_deviation_percent")) and float(trip["route_deviation_percent"]) >= 10):
        add("route_detour", "the route deviated from the planned one")
    if _positive(trip.get("cleaning_fee")) or trip.get("cleaning_fee_claimed") \
            or any(e and e.startswith("cleaning_") for e in events):
        add("cleaning_fee", "a cleaning fee was claimed")
    if events & {"speeding_alert", "harsh_braking_detected", "rider_reported_safety"}:
        add("safety_conduct", "a driving-safety alert or safety report was recorded")
    if "send" in str(trip.get("service_type") or "").lower():
        add("delivery", "the trip was a RydeSEND delivery")
    return out


def topics_for_case(context, dispute_type: str) -> dict[str, str]:
    """Core topics of the type, then data-triggered ones, each with why it was fetched."""
    out = {t: f"core topic for {dispute_type}" for t in TYPE_TOPICS.get(dispute_type, ())}
    for topic, reason in triggered_topics(context).items():
        out.setdefault(topic, reason)
    return out
