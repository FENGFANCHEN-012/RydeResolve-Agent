"""
Export decided disputes as training / analysis rows (JSONL), one per dispute.

Each row: the case (type, who filed, description, the facts summary the Judge saw), both
parties' history WITHOUT this dispute, the AI's verdict, the final outcome and who decided it,
and the fraud labels a human gave (confirmed / rejected flags on this dispute). Pending
disputes and pending flags are left out: only settled outcomes are labels.

    python scripts/export_training.py --out data/exports/training.jsonl
    python scripts/export_training.py --out x.jsonl --human-only   # only human-reviewed outcomes
"""
import argparse
import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from sqlalchemy import select  # noqa: E402

from src import config  # noqa: E402,F401  (loads .env)
from src.store.db import Ruling, Store  # noqa: E402
from src.store.people import (FLAG_CONFIRMED, FLAG_REJECTED, Dispute, UserFlag,  # noqa: E402
                              dispute_outcome, get_user_history)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    ap.add_argument("--human-only", action="store_true")
    args = ap.parse_args()

    store = Store()
    rows = []
    with store.session() as s:
        for d in s.scalars(select(Dispute).order_by(Dispute.filed_at, Dispute.dispute_id)):
            out = dispute_outcome(s, d.dispute_id)
            if out["outcome"] == "pending" or (args.human_only and out["decided_by"] != "human"):
                continue
            ruling = s.scalars(select(Ruling).where(Ruling.dispute_id == d.dispute_id)
                               .order_by(Ruling.id.desc()).limit(1)).first()
            flags = s.scalars(select(UserFlag).where(UserFlag.dispute_id == d.dispute_id,
                                                     UserFlag.status.in_([FLAG_CONFIRMED, FLAG_REJECTED])))
            rows.append({
                "dispute_id": d.dispute_id, "dispute_type": d.dispute_type, "filed_by": d.filed_by_role,
                "filed_at": d.filed_at, "description": d.description,
                "case_summary": ruling.case_summary if ruling else None,
                "filer_history": get_user_history(store, d.filer_id, d.dispute_id) if d.filer_id else None,
                "respondent_history": get_user_history(store, d.respondent_id, d.dispute_id) if d.respondent_id else None,
                "ai_verdict": ruling.verdict if ruling else None,
                "final_outcome": out["outcome"], "decided_by": out["decided_by"],
                "final_refund": out.get("refund_amount"), "human_reason": out.get("reason"),
                "fraud_labels": [{"user_id": f.user_id, "signal": f.signal, "label": f.status,
                                  "reason": f.review_reason} for f in flags],
            })
    os.makedirs(os.path.dirname(os.path.abspath(args.out)), exist_ok=True)
    with open(args.out, "w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    print(f"wrote {len(rows)} rows to {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
