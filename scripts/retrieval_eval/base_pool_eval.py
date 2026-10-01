"""How much of what each case needs reaches the agents? (D14)

For the 27 eval cases, compares the base clauses handed to every agent:
  complaint   the complaint search alone (top 5, tag-ranked) - before D14
  base        complaint + the type's core topics + data-triggered topics (Case Brief, cap 8)
Metrics over each case's expected_official_sections:
  recall      share of the expected sections present in the clauses
  all_found   every expected section present
No LLM; reads the live collection.   python scripts/retrieval_eval/base_pool_eval.py
"""
import asyncio
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
os.environ.setdefault("EXTRA_DISPUTE_DIRS", "data/eval_cases/heldout")

from src.agents.case_brief import CaseBriefAgent  # noqa: E402
from src.agents.collector import CollectorAgent  # noqa: E402
from src.integrations.ryde_api import RydeAPIClient, load_dispute_dataset  # noqa: E402
from src.rag.retriever import DocumentRetriever  # noqa: E402

ANSWER_KEYS = json.loads((ROOT / "data" / "eval_answer_keys.json").read_text(encoding="utf-8"))
OUT = ROOT / "data" / "eval" / "retrieval" / "base_pool.json"


def coverage(clauses: list[dict], gold: set[str]) -> dict:
    got = {f"{c.get('source')} > {c.get('section')}" for c in clauses}
    found = gold & got
    return {"recall": len(found) / len(gold), "all_found": found == gold, "missing": sorted(gold - got)}


async def main():
    api = RydeAPIClient()
    api.list_orders()
    retriever = DocumentRetriever()
    brief_agent = CaseBriefAgent(retriever=retriever)
    collector = CollectorAgent()
    rows = []
    for order_id, path in sorted(api._index.items()):
        data = load_dispute_dataset(path)
        did = (data.get("dispute_ticket") or {}).get("dispute_id") or order_id
        exp = data.get("expected_outcome") or ANSWER_KEYS.get(did) or {}
        gold = set(exp.get("expected_official_sections") or [])
        if not gold:
            continue
        ctx = await collector.collect_from_dataset(path)
        if ctx.type is None and exp.get("expected_dispute_type"):
            ctx = ctx.model_copy(update={"type": exp["expected_dispute_type"]})
        dtype = getattr(ctx.type, "value", ctx.type) or ""
        complaint = await asyncio.to_thread(retriever.retrieve_for_dispute, dispute_type=dtype,
                                            dispute_description=ctx.description or "")
        brief = await brief_agent.build(ctx)
        row = {"case": did, "type": dtype, "n_gold": len(gold), "topics": brief["topics"], "path": str(path),
               "base_sections": [f"{c.get('source')} > {c.get('section')}" for c in brief["clause_texts"]],
               "complaint": coverage(complaint, gold), "base": coverage(brief["clause_texts"], gold)}
        rows.append(row)
        print(f"{did:<12} complaint {row['complaint']['recall']:.2f} -> base {row['base']['recall']:.2f}"
              f"  missing {row['base']['missing']}")

    def avg(variant, metric):
        return round(sum(float(r[variant][metric]) for r in rows) / len(rows), 3)

    summary = {v: {"recall": avg(v, "recall"), "all_found": avg(v, "all_found")} for v in ("complaint", "base")}
    print(f"\n{len(rows)} cases  complaint-only: recall {summary['complaint']['recall']}, all found "
          f"{summary['complaint']['all_found']}  |  base (with topics): recall {summary['base']['recall']}, "
          f"all found {summary['base']['all_found']}")
    OUT.write_text(json.dumps({"summary": summary, "rows": rows}, indent=1, ensure_ascii=False), encoding="utf-8")


if __name__ == "__main__":
    asyncio.run(main())
