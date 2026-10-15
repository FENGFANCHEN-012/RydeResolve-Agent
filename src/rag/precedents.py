"""
Precedent index: human-reviewed past rulings, searchable by how similar the facts are.

Stored in its own Qdrant collection (PRECEDENT_COLLECTION, default "ryde_precedents")
with the same hybrid dense + BM25 search as the policy library. The text that is
embedded is the case summary (facts only), so a new case finds precedents by what
happened, not by how they were decided.

Visibility
- Live rulings see only "active" precedents.
- The evaluation gate also sees "staged" ones (PRECEDENTS_INCLUDE_STAGED=1), so a
  candidate can be tested before it is released.
- A case never sees precedents from its own family (the case and its evaluation
  variants), so the evaluation cannot be answered by its own answer key.

Which precedents are worth showing (search):
- Same dispute type as the case: a no-show ruling is no guide to a fare dispute.
- Decided under the governing policy now in force: a precedent stored under an older policy
  (or with no policy recorded) is never shown, so a policy change cannot be undone by old rulings.
- One precedent per principle: near-identical rulings would crowd out a different, relevant one.
- Then the most similar facts first (hybrid dense + BM25), at most top_k.
"""
import logging
import os

from src.core.governing_policy import SOURCE as POLICY_VERSION
from src.store.db import ACTIVE, STAGED, Precedent, case_family

logger = logging.getLogger(__name__)
COLLECTION = os.getenv("PRECEDENT_COLLECTION", "ryde_precedents")


def _visible_statuses() -> set[str]:
    return {ACTIVE, STAGED} if os.getenv("PRECEDENTS_INCLUDE_STAGED") == "1" else {ACTIVE}


def _chunk_id(precedent_id: int) -> str:
    return f"precedent-{precedent_id}"


class PrecedentIndex:
    def __init__(self, store=None):
        if store is None:
            from src.rag.qdrant_store import QdrantStore
            store = QdrantStore(collection_name=COLLECTION)
        self.store = store

    def upsert(self, p: Precedent) -> None:
        self.store.upsert([{
            "id": _chunk_id(p.id),
            "text": f"[{p.dispute_type or 'dispute'}] {p.case_summary}",
            "metadata": {"precedent_id": p.id, "dispute_id": p.dispute_id, "family": p.family,
                         "dispute_type": p.dispute_type, "verdict": p.verdict, "refund_amount": p.refund_amount,
                         "principle": p.principle, "status": p.status, "version": p.version,
                         "policy_version": POLICY_VERSION},
        }])

    def remove(self, precedent_id: int) -> None:
        self.store.delete([_chunk_id(precedent_id)])

    def search(self, case_summary: str, dispute_id: str, top_k: int = 3,
               dispute_type: str | None = None) -> list[dict]:
        """The most useful visible precedents for this case (see the module docstring)."""
        try:
            points = self.store.search_points(case_summary, limit=top_k * 6)
        except Exception as exc:  # no collection yet, or the store is down: rule without precedents
            logger.info("Precedent search skipped: %s", exc)
            return []
        family, visible = case_family(dispute_id), _visible_statuses()
        hits, principles = [], set()
        for p in points:  # already ranked by similarity
            m = p.payload
            if m.get("status") not in visible or m.get("family") == family:
                continue
            if m.get("policy_version") != POLICY_VERSION:
                continue
            if dispute_type and m.get("dispute_type") and m.get("dispute_type") != dispute_type:
                continue
            key = " ".join((m.get("principle") or "").lower().split())
            if key and key in principles:
                continue
            principles.add(key)
            hits.append(dict(m, score=round(p.score, 4)))
            if len(hits) == top_k:
                break
        return [{k: h.get(k) for k in ("precedent_id", "dispute_id", "dispute_type", "verdict", "refund_amount",
                                         "principle", "text", "version", "score")} for h in hits]


def summarize_case(context) -> str:
    """Deterministic fact summary of a case, used both to store a precedent and to find one.
    Built from the Collector's findings (each cites its source), not from anyone's argument."""
    ctx = context.model_dump() if hasattr(context, "model_dump") else dict(context)
    dispute_type = getattr(ctx.get("type"), "value", ctx.get("type")) or "dispute"
    lines = [f"{dispute_type} dispute filed by {ctx.get('reporter') or 'unknown'}.",
             f"Complaint: {(ctx.get('description') or '').strip()[:400]}"]
    for f in (ctx.get("findings") or [])[:10]:
        f = f.model_dump() if hasattr(f, "model_dump") else f
        lines.append(f"[{f.get('kind', 'fact')}] {f.get('statement', '')}")
    return "\n".join(lines)


_index: "PrecedentIndex | None" = None


def find_precedents(context, top_k: int = 3) -> list[dict]:
    """Precedents for the Judge. Never raises: with no index or no match, the Judge
    simply rules without precedents, exactly as before the feedback loop existed."""
    global _index
    if os.getenv("PRECEDENTS_ENABLED", "1") == "0":
        return []
    try:
        if _index is None:
            _index = PrecedentIndex()
        dispute_id = getattr(context, "dispute_id", None) or (context or {}).get("dispute_id", "")
        dtype = context.type if hasattr(context, "type") else (context or {}).get("type")
        dtype = getattr(dtype, "value", dtype)
        return _index.search(summarize_case(context), dispute_id, top_k=top_k, dispute_type=dtype)
    except Exception as exc:
        logger.info("Precedents unavailable: %s", exc)
        return []
