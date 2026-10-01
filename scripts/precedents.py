"""Admin tool for the precedent lifecycle (src/store/feedback.py).

    python scripts/precedents.py list [--status staged]
    python scripts/precedents.py approve 3 --actor alice
    python scripts/precedents.py release data/eval/<baseline> data/eval/<candidate> --actor alice
    python scripts/precedents.py retire 3 --actor alice --reason "caused a wrong ruling on NS-004"
    python scripts/precedents.py verify-audit

Release procedure: run the evaluation once as usual (the baseline), then once with
`python scripts/eval.py --with-staged-precedents` (the candidate). `release` compares the
two and moves every staged precedent to active if nothing got worse, else to rejected.
"""
import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.rag.precedents import PrecedentIndex  # noqa: E402
from src.store import feedback  # noqa: E402
from src.store.db import get_store  # noqa: E402


def _summary(run_dir: str) -> dict:
    return json.loads((Path(run_dir) / "summary.json").read_text(encoding="utf-8"))["summary"]


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    ls = sub.add_parser("list"); ls.add_argument("--status")
    a = sub.add_parser("approve"); a.add_argument("id", type=int); a.add_argument("--actor", required=True)
    r = sub.add_parser("release"); r.add_argument("baseline"); r.add_argument("candidate")
    r.add_argument("--actor", required=True)
    t = sub.add_parser("retire"); t.add_argument("id", type=int); t.add_argument("--actor", required=True)
    t.add_argument("--reason", required=True)
    sub.add_parser("verify-audit")
    args = ap.parse_args()
    store = get_store()

    if args.cmd == "list":
        for p in store.list_precedents(args.status):
            print(f"#{p.id:<4} {p.status:<9} {p.dispute_id:<12} AI {p.ai_verdict} -> human {p.verdict} "
                  f"{p.refund_amount}  | {p.principle[:70]}")
    elif args.cmd == "approve":
        p = feedback.approve(store, PrecedentIndex(), args.id, args.actor)
        print(f"#{p.id} staged. Run the candidate evaluation, then `release`.")
    elif args.cmd == "release":
        base, cand = _summary(args.baseline), _summary(args.candidate)
        passed, reasons, moved = feedback.release_staged(store, PrecedentIndex(), base, cand, args.actor,
                                                         args.baseline, args.candidate)
        print(("RELEASED" if passed else "REJECTED") + f" precedents {moved}")
        for why in reasons:
            print("  -", why)
    elif args.cmd == "retire":
        p = feedback.retire(store, PrecedentIndex(), args.id, args.actor, args.reason)
        print(f"#{p.id} retired.")
    elif args.cmd == "verify-audit":
        ok, bad = store.verify_audit_chain()
        print("audit log intact" if ok else f"audit log BROKEN at entry {bad}")


if __name__ == "__main__":
    main()
