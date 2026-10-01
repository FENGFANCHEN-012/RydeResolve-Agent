"""
Build the policy search query from verified case data instead of the complaint.

The complaint is the weakest query we have (Hit@1 0.60 in the retrieval A/B, D2): it is
emotional, and either party can steer the search with wording. An LLM rewrite was tried
and invented a "5 minutes" rule (D2). This builder is deterministic: it only uses

  - the classified dispute type's hint words (official help-centre vocabulary),
  - this trip's policy keys turned into words ("free cancellation within min of match"),
  - the Collector's fact and conflict statements, with times, dates and coordinates removed.

Nothing in it comes from either party's argument, so it cannot be steered or invent a rule.

Status: NOT used by the pipeline. It lost the A/B on the 27 eval cases (Hit@1 0.56 vs 0.82
for the complaint, D12): the findings are mostly measurements (km, speed, message counts),
not policy language. Kept for scripts/retrieval_eval/fact_query_eval.py and later work.
TYPE_HINTS is used by the retriever.
"""
import re

# Words from the official help-centre articles, so the hint pulls toward real rules
TYPE_HINTS = {
    "route_deviation": "fixed fare pick-up drop-off points route suggested by the rider",
    "no_show": "I'm Here waits more than 3 minutes rider no show cancellation fee waiver request",
    "no_show_charge": "I'm Here waits more than 3 minutes rider no show cancellation fee waiver request",
    "fare_dispute": "fare structure fixed fare ERP toll transaction fee overcharged",
    "cancellation_refund": "cancellation fee 3 minutes of matching grace period cancellation fee waiver request",
    "service_quality": "feedback about my driver report a safety issue code of conduct",
    "property_damage": "mess professional cleaning fee",
    "safety_incident": "report a safety issue harassment code of conduct",
    "driver_rights": "rider made a mess cleaning claim receipt photo appeal",
    "accident_liability": "accident insurance coverage who bears financial costs",
}

# Timestamps, clock times, dates, coordinates and finding sources carry no policy meaning
_NOISE = re.compile(
    r"\(\s*sources?:[^)]*\)"                       # "(sources: gps_trace[3], ...)"
    r"|\d{4}-\d{2}-\d{2}T[\d:.+\-]+"               # ISO timestamps
    r"|\b\d{1,2}:\d{2}(?::\d{2})?\b"               # 17:59 / 17:59:05
    r"|\b\d{4}-\d{2}-\d{2}\b"                      # dates
    r"|-?\d+\.\d{3,}"                              # coordinates
    r"|\[[^\]]*\]"                                 # [ids]
)
_MAX_FINDINGS = 8


def _clean(statement: str) -> str:
    text = _NOISE.sub(" ", statement or "")
    text = re.sub(r"[()]", " ", text)
    return re.sub(r"\s+", " ", text).strip(" .,;")


def _get(obj, key):
    return obj.get(key) if isinstance(obj, dict) else getattr(obj, key, None)


def build_fact_query(context, dispute_type: str | None = None) -> str:
    """The search text for a dispute, built only from platform data. Empty string when the
    context has nothing usable (the caller then falls back to the complaint query)."""
    dtype = dispute_type or getattr(_get(context, "type"), "value", _get(context, "type")) or ""
    parts = [TYPE_HINTS.get(dtype, "")]

    policy = _get(context, "platform_policy") or {}
    parts += [k.replace("_", " ") for k in policy if isinstance(k, str) and not k.startswith("_")]

    findings = [f if isinstance(f, dict) else f.model_dump() for f in (_get(context, "findings") or [])]
    # Conflicts first: they are what the dispute turns on
    findings.sort(key=lambda f: {"conflict": 0, "fact": 1}.get(f.get("kind"), 2))
    parts += [_clean(f.get("statement", "")) for f in findings
              if f.get("kind") in ("fact", "conflict")][:_MAX_FINDINGS]

    query = " ".join(p for p in parts if p)
    return query if query != TYPE_HINTS.get(dtype, "") else ""
