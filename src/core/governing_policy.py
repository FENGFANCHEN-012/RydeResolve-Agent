"""Ryde Dispute Resolution Policy v2.1: the governing dispute policy (D50).

The organisers' policy for RydeResolve agents (data/policies/governing/), as opposed to the public
Help Centre pages in data/policies/official/. It is short and every section matters to the ruling,
so it is not searched: the sections that apply to a case are put into the Case Brief in full, ahead
of the retrieved help-centre clauses, and cited as `ryde_dispute_policy_v2.1#<section>` (e.g.
`#1.3`). Which sections apply follows the dispute type and the trip's records; the ruling
thresholds (section 6) always apply.
"""
from __future__ import annotations

import re
from functools import lru_cache
from pathlib import Path

SOURCE = "ryde_dispute_policy_v2.1"
POLICY_FILE = Path(__file__).resolve().parents[2] / "data" / "policies" / "governing" / \
    "ryde_dispute_resolution_policy_v2_1.md"

_SECTION_RE = re.compile(r"^### (?:Precedent )?(\d+\.\d+)[:\s]+(.*)$")
_CLEANING_WORDS = re.compile(r"\b(clean\w*|vomit\w*|stain\w*|spill\w*|soil\w*|mess\w*|damage\w*|repair\w*)\b", re.I)
_SAFETY_WORDS = re.compile(r"\b(unsafe|harass\w*|assault\w*|threat\w*|reckless|dangerous|accident|touch\w*)\b", re.I)

BY_TYPE = {
    "route_deviation": ["1.1", "1.2", "1.3", "1.4", "7.1"],
    "no_show": ["2.1", "2.2", "2.3", "2.4", "2.5", "7.3"],
    "cancellation_refund": ["2.1", "2.2", "2.3", "2.4", "7.3"],
    "fare_dispute": ["3.1", "3.2", "3.3", "3.4", "3.5", "7.2"],
}
PROPERTY = ["4.1", "4.2", "4.3", "4.4"]
SAFETY = ["5.1", "5.2", "5.3"]
THRESHOLDS = ["6.1", "6.2", "6.3"]


@lru_cache(maxsize=1)
def sections() -> dict[str, dict]:
    """Section number -> {title, text}; text is the section as written, heading included."""
    if not POLICY_FILE.is_file():
        return {}
    out: dict[str, dict] = {}
    current = None
    for line in POLICY_FILE.read_text(encoding="utf-8").splitlines():
        m = _SECTION_RE.match(line)
        if m:
            current = m.group(1)
            out[current] = {"title": m.group(2).strip(), "lines": [line.lstrip("# ").strip()]}
        elif line.startswith("## ") or line.startswith("---"):
            current = None
        elif current:
            out[current]["lines"].append(line)
    return {k: {"title": v["title"], "text": "\n".join(v["lines"]).strip()} for k, v in out.items()}


def is_property_case(ctx: dict) -> bool:
    trip = ctx.get("trip") or {}
    fees = [trip.get(k) for k in ("cleaning_fee", "cleaning_fee_claimed", "damage_fee", "repair_fee")]
    return any(isinstance(f, (int, float)) and f > 0 for f in fees) or \
        bool(_CLEANING_WORDS.search(str(ctx.get("description") or "")))


def is_safety_case(ctx: dict, dispute_type: str, urgency: str | None = None) -> bool:
    return urgency == "P0" or dispute_type == "accident_liability" or \
        bool(_SAFETY_WORDS.search(str(ctx.get("description") or "")))


def applicable(ctx: dict, dispute_type: str, urgency: str | None = None) -> list[str]:
    """Section numbers that govern this case, in policy order."""
    trip = ctx.get("trip") or {}
    wanted = set(THRESHOLDS) | set(BY_TYPE.get(dispute_type, []))
    if trip.get("surge_pricing_log") or (isinstance(trip.get("fare_breakdown"), dict)
                                         and "surge" in str(trip["fare_breakdown"]).lower()):
        wanted |= set(BY_TYPE["fare_dispute"])
    if trip.get("recommended_route") or trip.get("traffic_incidents"):
        wanted |= set(BY_TYPE["route_deviation"])
    if trip.get("cancellation_time"):
        wanted |= set(BY_TYPE["no_show"])
    if is_property_case(ctx):
        wanted |= set(PROPERTY)
    if is_safety_case(ctx, dispute_type, urgency):
        wanted |= set(SAFETY)
    have = sections()
    return sorted((s for s in wanted if s in have), key=lambda s: tuple(int(x) for x in s.split(".")))


def clauses_for(ctx: dict, dispute_type: str, urgency: str | None = None) -> list[dict]:
    """The governing sections as clauses in the retriever's shape (citable by reference)."""
    have = sections()
    return [{"source": SOURCE, "chunk_index": s, "section": f"s{s} {have[s]['title']}",
             "clause": have[s]["text"], "governing": True, "found_by": ["governing policy v2.1"]}
            for s in applicable(ctx, dispute_type, urgency)]
