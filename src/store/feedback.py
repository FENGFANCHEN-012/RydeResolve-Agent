"""
Learning feedback loop: how a human correction becomes a precedent, and how a
precedent is released only after the evaluation shows it does no harm.

    reviewer overrides a ruling  -> pending   (Store.submit_review)
    admin approves               -> staged    (indexed; only the evaluation sees it)
    evaluation gate passes       -> active    (live rulings see it)
    evaluation gate fails        -> rejected
    admin retires an active one  -> retired   (removed from the index: rollback)

Every step is written to the hash-chained audit log.
"""
from src.store.db import ACTIVE, PENDING, REJECTED, RETIRED, STAGED, Store

# Metrics that must never get worse: a precedent that trades safety for accuracy is rejected
HARD_METRICS = ("p0_escalation_recall", "refund_cap_ok", "missing_data_escalation", "failure_rate")


def approve(store: Store, index, precedent_id: int, approver: str):
    """A human approves a pending precedent. It is indexed as staged, not yet live."""
    p = store.set_status(precedent_id, STAGED, approver, allowed_from=(PENDING,))
    index.upsert(p)
    return p


def retire(store: Store, index, precedent_id: int, actor: str, reason: str):
    """Roll back a live precedent."""
    p = store.set_status(precedent_id, RETIRED, actor, allowed_from=(ACTIVE, STAGED),
                         gate_result={"retired_because": reason})
    index.remove(precedent_id)
    return p


def gate(baseline: dict, candidate: dict) -> tuple[bool, list[str]]:
    """Compare two eval summaries (summary.json["summary"]) run on the same cases.
    Pass only if verdict accuracy does not drop, overall or on the held-out set,
    and no hard safety metric gets worse."""
    reasons = []
    bm, cm = baseline["metrics"], candidate["metrics"]
    for name in HARD_METRICS:
        b, c = (bm.get(name) or {}).get("value"), (cm.get(name) or {}).get("value")
        if b is None or c is None:
            continue
        worse = c > b if name == "failure_rate" else c < b
        if worse:
            reasons.append(f"{name} got worse: {b} -> {c}")
    b, c = bm["verdict_accuracy"]["value"], cm["verdict_accuracy"]["value"]
    if c < b:
        reasons.append(f"verdict_accuracy dropped: {b} -> {c}")
    bh = (baseline.get("by_set") or {}).get("heldout", {}).get("verdict_accuracy")
    ch = (candidate.get("by_set") or {}).get("heldout", {}).get("verdict_accuracy")
    if bh is not None and ch is not None and ch < bh:
        reasons.append(f"held-out verdict_accuracy dropped: {bh} -> {ch}")
    return not reasons, reasons


def release_staged(store: Store, index, baseline: dict, candidate: dict, actor: str,
                   baseline_run: str, candidate_run: str) -> tuple[bool, list[str], list[int]]:
    """Apply the gate to every staged precedent at once (they were evaluated together)."""
    passed, reasons = gate(baseline, candidate)
    result = {"passed": passed, "reasons": reasons, "baseline_run": baseline_run, "candidate_run": candidate_run}
    moved = []
    for p in store.list_precedents(STAGED):
        store.set_status(p.id, ACTIVE if passed else REJECTED, actor, allowed_from=(STAGED,), gate_result=result)
        if passed:
            index.upsert(store.get_precedent(p.id))  # payload status -> active
        else:
            index.remove(p.id)
        moved.append(p.id)
    return passed, reasons, moved
