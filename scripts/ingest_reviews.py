"""Turn reviewer decisions on evaluated cases into pending (or staged) precedents.

    python scripts/ingest_reviews.py data/eval/<run> reviews.json --reviewer "..." [--approve --approver "..."]

The evaluation does not record rulings (RECORD_RULINGS=0), so this replays the saved
traces into the record store as rulings, then submits each reviewer decision through
`Store.submit_review`, exactly as the review desk would. An override, or any decision on
an escalated case, becomes a pending precedent (src/store/feedback.py). With --approve
each new precedent is approved, which indexes it as staged: only an evaluation run with
--with-staged-precedents sees it until `scripts/precedents.py release` passes the gate.

reviews.json: a list of {"dispute_id", "action": "confirm"|"override", "final_verdict",
"final_refund", "reason"}. The reason becomes the precedent's principle.
"""
import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.rag.precedents import PrecedentIndex, summarize_case  # noqa: E402
from src.store import feedback  # noqa: E402
from src.store.db import get_store  # noqa: E402


def _from_trace(path: Path) -> dict:
    """The Collector's context, the Judge's last ruling and the final status of one saved run."""
    events = json.loads(path.read_text(encoding="utf-8"))
    ends = [e for e in events if e.get("type") == "step_end"]
    context = next(e["output"] for e in ends if e.get("agent") == "Collector")
    judge = [e["output"] for e in ends if e.get("agent") == "Arbitrator"]
    result = next(e["result"] for e in events if e.get("type") == "result")
    classification = result.get("classification") or {}
    return {"context": context, "decision": judge[-1] if judge else {}, "result": result,
            "dispute_type": classification.get("dispute_type") or context.get("type")}


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("run_dir")
    ap.add_argument("reviews")
    ap.add_argument("--reviewer", required=True)
    ap.add_argument("--approve", action="store_true", help="Also approve each new precedent (-> staged)")
    ap.add_argument("--approver")
    args = ap.parse_args()
    if args.approve and not args.approver:
        ap.error("--approve needs --approver")

    store, index = get_store(), (PrecedentIndex() if args.approve else None)
    run = Path(args.run_dir)
    for rv in json.loads(Path(args.reviews).read_text(encoding="utf-8")):
        trace = run / "traces" / f"{rv['dispute_id']}_r1.json"
        t = _from_trace(trace)
        d, r = t["decision"], t["result"]
        ruling = store.record_ruling(
            dispute_id=r.get("dispute_id") or rv["dispute_id"], order_id=r.get("order_id"),
            dispute_type=t["dispute_type"], status=r.get("status") or "unknown",
            verdict=d.get("verdict"), refund_amount=d.get("refund_amount"), confidence=d.get("confidence"),
            rationale=d.get("rationale"), policy_refs=list(d.get("policy_references") or []),
            precedent_ids=[], case_summary=summarize_case(t["context"]), pipeline_version=f"eval:{run.name}")
        _, precedent = store.submit_review(ruling.id, args.reviewer, rv["action"], rv["reason"],
                                           final_verdict=rv.get("final_verdict"),
                                           final_refund=rv.get("final_refund"))
        line = f"{rv['dispute_id']:<8} AI {ruling.status}/{ruling.verdict} -> {rv['action']} {rv.get('final_verdict')}"
        if precedent is None:
            print(line + "  (confirmed resolved ruling: no precedent)")
            continue
        if args.approve:
            feedback.approve(store, index, precedent.id, args.approver)
            print(line + f"  precedent #{precedent.id} staged")
        else:
            print(line + f"  precedent #{precedent.id} pending")


if __name__ == "__main__":
    main()
