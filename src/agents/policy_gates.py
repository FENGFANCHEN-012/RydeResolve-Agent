"""Routing rules of Ryde Dispute Resolution Policy v2.1 that code enforces (D50).

The policy says which disputes an AI ruling may settle and which go to a person. These are checked
in code after the Judge rules (and after the code Judge), never left to the model:

- s5.2   safety incidents: AI agents may not rule at all (a threat found in the chat included).
- s6.1   dispute value above S$50: always a person; S$10-50: a person unless confidence >= 0.80.
- s6.3   a party with a fraud flag: confidence must be >= 0.95. The no-show / cancellation category
         is exempt: s6.2 makes the AI ruling final there, with no confidence requirement to raise.
- s4.4   a rider disputing a cleaning or damage claim: a person reviews it.

Not enforced: s6.2's "route deviation over 2 km escalates". The organisers' own sample DISP-001
(4.3 km) expects an automatic partial refund, and the sample is followed (D50).
A gate never changes the ruling; it only sends the case to a person, with the section as reason.
"""
from __future__ import annotations

import re

from src.agents.safety import harassment_in_claim
from src.core.governing_policy import CLAIM_FIELDS, is_property_case

AUTO_FINAL_BELOW = 10.0     # s6.1: under S$10 the AI ruling is final
ALWAYS_HUMAN_ABOVE = 50.0   # s6.1: above S$50 always human review
MID_CONFIDENCE = 0.80       # s6.1: S$10-50 needs 80%+
FRAUD_CONFIDENCE = 0.95     # s6.3


def _get(context, key):
    return context.get(key) if isinstance(context, dict) else getattr(context, key, None)


def dispute_value(decision, context) -> float:
    """The amount at stake: every charge on the filer the records name, a driver's own claim, or
    the refund the Judge set, whichever is largest."""
    from src.agents.case_brief import disputed_total
    trip = _get(context, "trip") or {}
    values = [disputed_total(context) or 0.0]
    if str(_get(context, "reporter") or "").lower() == "driver":
        values += [float(trip[k]) for k in CLAIM_FIELDS
                   if isinstance(trip.get(k), (int, float))]
    try:
        values.append(float(getattr(decision, "refund_amount", None) or 0))
    except (TypeError, ValueError):
        pass
    return round(max(values), 2)


# s5.1 / s5.2: safety keywords or indicators flag a dispute whatever its type. OF-16 ("weaving
# between lanes ... tailgating and braking hard", speeding alerts) was ruled as a fare dispute.
_SAFETY_TEXT = re.compile(
    r"\b(reckless\w*|dangerous(ly)?|weav(e|ed|ing)|tailgat\w*|speeding|harass\w*|assault\w*|threat\w*|"
    r"unsafe|inappropriate(ly)?|accident|crash(ed)?|collision|attack\w*)\b", re.I)
_SAFETY_EVENTS = {"speeding_alert", "harsh_braking_detected", "crash_detected", "sos_triggered", "safety_report"}


def safety_indicators(context) -> list[str]:
    """What marks this dispute as a safety incident under s5.1-5.2: words in the complaint, or
    driving-safety events in the platform record."""
    found = [m.group(0).lower() for m in _SAFETY_TEXT.finditer(str(_get(context, "description") or ""))]
    found += harassment_in_claim(_get(context, "description"))   # D66: harassment in plain words
    found += [e.get("event_type") for e in _get(context, "app_events") or []
              if isinstance(e, dict) and e.get("event_type") in _SAFETY_EVENTS]
    return sorted(set(found))


def _no_show_category(context) -> bool:
    t = _get(context, "type")
    t = getattr(t, "value", t)
    return t in ("no_show", "cancellation_refund") or bool((_get(context, "trip") or {}).get("cancellation_time"))


def check(decision, context, urgency: str | None = None) -> list[str]:
    """Reasons, each naming its v2.1 section, why this case must go to a person; empty when the AI
    ruling may stand."""
    if decision is None or getattr(decision, "human_review_needed", False):
        return []
    reasons = []
    safety = _get(context, "safety") or {}
    if urgency == "P0" or _get(context, "safety_alerts") or (isinstance(safety, dict) and safety.get("tier")) \
            or safety_indicators(context):
        reasons.append("Policy v2.1 s5.2: a safety incident; AI agents may prepare the case but not rule on it.")
    value = dispute_value(decision, context)
    try:
        confidence = float(getattr(decision, "confidence", 0) or 0)
    except (TypeError, ValueError):
        confidence = 0.0
    if value > ALWAYS_HUMAN_ABOVE:
        reasons.append(f"Policy v2.1 s6.1: the dispute value S${value:.2f} is above S${ALWAYS_HUMAN_ABOVE:.0f}; "
                       "always human review.")
    elif value >= AUTO_FINAL_BELOW and confidence < MID_CONFIDENCE:
        reasons.append(f"Policy v2.1 s6.1: the dispute value S${value:.2f} is S$10-50 and the ruling's "
                       f"confidence {confidence:.2f} is below {MID_CONFIDENCE:.2f}.")
    flagged = [who for who in ("rider_profile", "driver_profile")
               if isinstance(_get(context, who), dict) and (_get(context, who).get("fraud_flags") or 0) >= 1]
    if flagged and confidence < FRAUD_CONFIDENCE and not _no_show_category(context):
        names = " and ".join(w.split("_")[0] for w in flagged)
        reasons.append(f"Policy v2.1 s6.3: the {names} has a fraud flag, so a ruling needs confidence "
                       f"{FRAUD_CONFIDENCE:.2f}; this one has {confidence:.2f}.")
    if is_property_case({"trip": _get(context, "trip"), "description": _get(context, "description")}) and \
            str(_get(context, "reporter") or "").lower() in ("rider", "passenger"):
        reasons.append("Policy v2.1 s4.4: a rider disputes a cleaning or damage claim; it is routed to "
                       "human review.")
    return reasons
