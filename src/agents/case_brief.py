"""
Case Brief agent: one shared dossier per dispute, built after classification.

Before this step each advocate saw raw trip / chat / GPS JSON and the retrieved
help-centre clauses, but not the Collector's findings, the app event timeline
or this trip's own policy parameters (e.g. no_show_threshold_min). Only the
Judge got them, buried in a raw JSON dump. Eval run 20260930-132225 showed the
cost: the Judge ruled on an "arrived" event the Collector had already flagged
as contradicted by GPS (NS-002-C1), and the Policy agent missed a case rule it
never saw (FD-002-C3).

The brief puts the same verified material in front of every agent:
  - dispute type and urgency (Classifier)
  - facts, conflicts and data gaps with their sources (Collector tools)
  - this trip's platform rules, citable as platform_policy.<key>
  - the app event timeline
  - the official policy clauses found for the case (one RAG search)

No LLM is used: the brief costs no tokens and cannot invent a fact. The search
uses the same query as the agents, so their later lookups hit the retriever's
per-dispute cache instead of searching again.
"""
import asyncio
import logging

from src.core.trace import record_retrieval
from src.rag.policy_topics import topics_for_case

logger = logging.getLogger(__name__)

# Keep the brief small: it goes into every prompt of the debate
_MAX_FINDINGS_PER_KIND = 12
_MAX_EVENTS = 20
# Base clauses handed to every agent (each is cut to 500 characters in the prompts)
MAX_BASE_CLAUSES = 10
_COMPLAINT_FIRST = 3     # complaint hits placed before the topic hits


# Sources that only locate a record, not the disputed value itself
_NEUTRAL_SOURCES = {"trip.pickup_location", "trip.dropoff_location", "app_events", "gps_trace"}


def _disputed_sources(conflicts: list[dict], app_events: list) -> set[str]:
    """Records that a conflict calls into question. The arrival is recorded twice (trip field
    and driver_arrived event), so an arrival conflict disputes both."""
    disputed = {src for c in conflicts for src in c.get("sources") or []} - _NEUTRAL_SOURCES
    if any("arrival" in (c.get("id") or "") for c in conflicts):
        disputed.add("trip.driver_arrival_time")
        disputed.update(f"app_events[{i}]" for i, e in enumerate(app_events or [])
                        if isinstance(e, dict) and e.get("event_type") == "driver_arrived")
    return disputed


def _dump(obj) -> dict:
    return obj.model_dump() if hasattr(obj, "model_dump") else dict(obj or {})


class CaseBriefAgent:
    """Builds the shared case brief. `retriever` is injectable for tests."""

    def __init__(self, retriever=None):
        self.name = "CaseBrief"
        self._retriever = retriever

    def _get_retriever(self):
        if self._retriever is None:
            from src.rag.retriever import DocumentRetriever
            self._retriever = DocumentRetriever()
        return self._retriever

    async def _clauses(self, dispute_type: str, description: str, topics: dict[str, str]) -> list[dict]:
        """Base clauses: the complaint search plus one search per topic (the type's core topics
        and those the platform data triggers, D14). Each clause records why it was fetched.
        An unavailable index gives fewer clauses, never an error."""
        try:
            retriever = self._get_retriever()
        except Exception as exc:
            logger.warning("Case brief retrieval failed: %s", exc)
            return []
        try:
            complaint = await asyncio.to_thread(
                retriever.retrieve_for_dispute,
                dispute_type=dispute_type,
                dispute_description=description,
            ) or []
        except Exception as exc:
            logger.warning("Case brief complaint search failed: %s", exc)
            complaint = []
        per_topic = {}
        for topic in topics:
            try:
                from src.rag.retriever import retrieve_topic
                per_topic[topic] = await asyncio.to_thread(retrieve_topic, retriever, topic)
            except Exception as exc:
                logger.warning("Topic search %s failed: %s", topic, exc)
                per_topic[topic] = []

        # Order: best complaint hits, then the best hit of each topic, then the rest; no duplicates
        tagged = [(c, "complaint") for c in complaint[:_COMPLAINT_FIRST]]
        tagged += [(hits[0], f"topic {t}: {topics[t]}") for t, hits in per_topic.items() if hits]
        tagged += [(c, "complaint") for c in complaint[_COMPLAINT_FIRST:]]
        tagged += [(c, f"topic {t}: {topics[t]}") for t, hits in per_topic.items() for c in hits[1:]]
        merged: dict[tuple, dict] = {}
        for clause, why in tagged:
            key = (clause.get("source"), clause.get("chunk_index"), clause.get("section"))
            if key in merged:
                merged[key]["found_by"].append(why)
            elif len(merged) < MAX_BASE_CLAUSES:
                merged[key] = {**clause, "found_by": [why]}
        clauses = list(merged.values())
        record_retrieval(dispute_type, clauses)
        return clauses

    async def build(self, context, classification=None) -> dict:
        ctx = _dump(context)
        cls = _dump(classification) if classification is not None else {}
        dispute_type = getattr(ctx.get("type"), "value", ctx.get("type")) or "unknown"
        topics = topics_for_case(ctx, dispute_type)
        clauses = await self._clauses(dispute_type, ctx.get("description") or "", topics)

        findings = [_dump(f) for f in ctx.get("findings") or []]

        def pick(kind):
            return [{"id": f.get("id"), "statement": f.get("statement"), "sources": f.get("sources") or []}
                    for f in findings if f.get("kind") == kind][:_MAX_FINDINGS_PER_KIND]

        conflicts = pick("conflict")
        # A fact computed from a contradicted record (e.g. a wait timed from a disputed
        # arrival, eval case NS-002-C1) must not read as verified
        disputed = _disputed_sources(conflicts, ctx.get("app_events"))
        facts = [{**f, "disputed": bool(disputed & set(f["sources"]))} for f in pick("fact")]

        urgency = cls.get("urgency")
        return {
            "dispute_type": dispute_type,
            "urgency": getattr(urgency, "value", urgency),
            "facts": facts,
            "conflicts": conflicts,
            "gaps": pick("gap"),
            "case_rules": {f"platform_policy.{k}": v for k, v in (ctx.get("platform_policy") or {}).items()
                           if isinstance(k, str) and not k.startswith("_")},
            "timeline": [{"time": e.get("timestamp"), "event": e.get("event_type"),
                          "detail": {k: v for k, v in e.items() if k not in ("timestamp", "event_type")}}
                         for e in (ctx.get("app_events") or [])[:_MAX_EVENTS] if isinstance(e, dict)],
            "topics": topics,
            "clauses": [{"reference": f"{c.get('source', 'unknown')}#{c.get('chunk_index', i)}",
                         "section": c.get("section"), "found_by": c.get("found_by", [])}
                        for i, c in enumerate(clauses)],
            # Full text, handed to every agent instead of each one searching (base clauses)
            "clause_texts": [dict(c) for c in clauses],
        }


def render_clauses(clauses: list[dict]) -> str:
    """Policy clauses as compact text, one block per clause: "[reference] section" then the text
    (cut to 500 characters, whitespace collapsed). Indented JSON cost about 25% more tokens for
    the same content (D15). References are exactly the ones agents must cite."""
    blocks = []
    for i, c in enumerate(clauses):
        ref = c.get("reference") or f"{c.get('source', 'unknown')}#{c.get('chunk_index', i)}"
        text = " ".join(str(c.get("clause", "")).split())[:500]
        blocks.append(f"[{ref}] {c.get('section', '')}\n{text}")
    return "\n\n".join(blocks)


def render_case_brief(context, with_clause_list: bool = True, with_requested_text: bool = True) -> str:
    """The brief as a prompt section; empty string when the context has none
    (e.g. an agent called outside the workflow), so prompts stay as before.
    with_clause_list=False drops the list of clause references, for prompts that already
    carry the clauses' full text (the same references would be listed twice).
    with_requested_text=False lists requested clauses by name only (the research step, D24)."""
    brief = getattr(context, "case_brief", None)
    if brief is None and isinstance(context, dict):
        brief = context.get("case_brief")
    if not brief:
        return ""
    lines = ["=== CASE BRIEF (shared by every agent; built from platform data, not from either party) ===",
             f"Dispute type: {brief.get('dispute_type')}"
             + (f" (urgency {brief['urgency']})" if brief.get("urgency") else "")]

    def section(title, items):
        if items:
            lines.append(title)
            lines.extend(f"- [{f['id']}] {f['statement']}"
                         + (f" (sources: {', '.join(f['sources'])})" if f.get("sources") else "")
                         for f in items)

    facts = brief.get("facts") or []
    section("Verified facts (computed by deterministic tools):", [f for f in facts if not f.get("disputed")])
    section("Facts computed FROM A DISPUTED RECORD (only as reliable as that record; see CONFLICTS):",
            [f for f in facts if f.get("disputed")])
    section("CONFLICTS between sources (a record contradicted by another source is NOT proven; "
            "rule on what the sources can support):", brief.get("conflicts"))
    section("Data gaps (evidence that does not exist; do not assume it):", brief.get("gaps"))
    rules = brief.get("case_rules") or {}
    if rules:
        lines.append("This trip's platform rules (cite by the exact key; where they speak they take "
                     "precedence over general help-centre text):")
        lines.extend(f"- {k} = {v}" for k, v in rules.items())
    if brief.get("timeline"):
        lines.append("App event timeline:")
        lines.extend(f"- {e['time']} {e['event']}" + (f" {e['detail']}" if e.get("detail") else "")
                     for e in brief["timeline"])
    if brief.get("clauses") and with_clause_list:
        lines.append("Official policy clauses found for this case (full text is given separately):")
        lines.extend(f"- {c['reference']} ({c['section']})"
                     + (f" - found by: {'; '.join(c['found_by'])}" if c.get("found_by") else "")
                     for c in brief["clauses"])
    requested = [c for c in brief.get("clause_texts") or [] if c.get("requested")]
    if requested:
        lines.append("Clauses requested during the debate (shared with both sides):")
        lines.extend(f"- {c.get('source')}#{c.get('chunk_index')} ({c.get('section')})"
                     + (": " + " ".join(str(c.get("clause", "")).split())[:500] if with_requested_text else "")
                     for c in requested)
    lines.append("=== END OF CASE BRIEF ===")
    return "\n".join(lines)


MAX_REQUESTS_PER_SIDE = 2


def valid_requests(analysis) -> list[str]:
    """Catalogue topics an advocate asked for; anything else is ignored, at most 2."""
    from src.rag.policy_topics import TOPICS
    raw = analysis.get("policy_requests") if isinstance(analysis, dict) else None
    out = []
    for t in raw if isinstance(raw, list) else []:
        t = str(t).strip().lower()
        if t in TOPICS and t not in out:
            out.append(t)
    return out[:MAX_REQUESTS_PER_SIDE]


async def add_requested_clauses(context, requests: dict[str, list[str]], retriever):
    """Return (context with the requested clauses added to its brief, list of new clauses).
    Every requested clause goes into the SHARED pool: both sides and the Judge see it, so an
    advocate cannot argue from a rule only it has read. Already-present clauses are not repeated."""
    from src.rag.retriever import retrieve_topic
    brief = dict(getattr(context, "case_brief", None) or {})
    if not brief or not any(requests.values()):
        return context, []
    texts = list(brief.get("clause_texts") or [])
    refs = list(brief.get("clauses") or [])
    have = {(c.get("source"), c.get("chunk_index"), c.get("section")): i for i, c in enumerate(texts)}
    added = []
    for side, topics in requests.items():
        for topic in topics:
            try:
                hits = await asyncio.to_thread(retrieve_topic, retriever, topic)
            except Exception as exc:
                logger.warning("Requested topic %s failed: %s", topic, exc)
                continue
            for c in hits:
                key = (c.get("source"), c.get("chunk_index"), c.get("section"))
                why = f"requested by {side}: {topic}"
                if key in have:
                    texts[have[key]].setdefault("found_by", []).append(why)
                    continue
                have[key] = len(texts)
                clause = {**c, "found_by": [why], "requested": True}
                texts.append(clause)
                refs.append({"reference": f"{c.get('source', 'unknown')}#{c.get('chunk_index', 0)}",
                             "section": c.get("section"), "found_by": [why]})
                added.append(clause)
    fetched = list(brief.get("fetched_topics") or [])
    fetched += [t for ts in requests.values() for t in ts if t not in fetched]
    brief.update({"clause_texts": texts, "clauses": refs, "fetched_topics": fetched,
                  "requests": {s: t for s, t in requests.items() if t}})
    return context.model_copy(update={"case_brief": brief}), added


# Raw context fields whose content the brief already carries (as computed facts, the event
# timeline and the case rules). With a brief they are left out of prompts: the same data was
# sent twice per prompt, and the raw GPS points made each agent re-derive distances (D15).
SUMMARISED_FIELDS = ("gps_trace", "findings", "app_events", "platform_policy")


def _finding_values(context, finding_id: str) -> dict | None:
    for f in (context or {}).get("findings") or [] if isinstance(context, dict) else getattr(context, "findings", []) or []:
        f = f if isinstance(f, dict) else f.model_dump()
        if f.get("id") == finding_id:
            return f.get("value") or {}
    return None


def disputed_charge(context) -> float | None:
    """The full amount in dispute, from platform data only: the fee that was charged, or what was
    charged above the quoted fare. None when the data names no single amount."""
    fee = _finding_values(context, "fee_check.charged")
    if fee and fee.get("fee"):
        return round(float(fee["fee"]), 2)
    fare = _finding_values(context, "fare_check.quoted_vs_charged")
    if fare and (fare.get("difference") or 0) > 0:
        return round(float(fare["difference"]), 2)
    return None


def has_brief(context) -> bool:
    brief = getattr(context, "case_brief", None)
    if brief is None and isinstance(context, dict):
        brief = context.get("case_brief")
    return bool(brief)


def gps_line(context) -> str:
    """The GPS part of a prompt: the raw points without a brief, a pointer to the brief with one."""
    gps = getattr(context, "gps_trace", None)
    if not gps:
        return "GPS trace: N/A"
    if has_brief(context):
        return (f"GPS trace: {len(gps)} points; distances, arrival and waiting times computed "
                "from them are in the CASE BRIEF")
    import json
    return f"GPS trace: {json.dumps(gps)}"


def brief_clauses(context) -> list[dict] | None:
    """The base clauses the brief found, in the retriever's dict shape; None when the context
    has no brief (an agent called outside the workflow then searches by itself)."""
    brief = getattr(context, "case_brief", None)
    if brief is None and isinstance(context, dict):
        brief = context.get("case_brief")
    if not brief or "clause_texts" not in brief:
        return None
    return [dict(c) for c in brief["clause_texts"]]


def case_rule_refs(context) -> set[str]:
    """platform_policy.<key> references an agent may cite for this case."""
    brief = getattr(context, "case_brief", None)
    if brief is None and isinstance(context, dict):
        brief = context.get("case_brief")
    return set((brief or {}).get("case_rules") or {})
