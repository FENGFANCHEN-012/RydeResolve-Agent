"""A/B the dispute search query and the section-tag ranking on the 27 eval cases (D12).

For each case the Collector runs offline (no LLM) and two queries are searched once in the
live Qdrant collection (read only):
  complaint  description + type hint        (what the pipeline used until now)
  facts      type hint + case-policy keys + Collector facts/conflicts (src/rag/query_builder.py)
Variants re-rank those candidate lists locally:
  complaint / facts / merged (RRF of both), each with a tag weight w:
  score = RRF + w * tag, tag = +1 when the chunk is tagged with the case type or "general",
  -1 when tagged "none", 0 otherwise. w = 0 is plain retrieval; tags only rank, never filter.
Gold = the case's expected_official_sections.

    LLM_PROVIDER is irrelevant (no LLM).  python scripts/retrieval_eval/fact_query_eval.py
"""
import asyncio
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
os.environ.setdefault("EXTRA_DISPUTE_DIRS", "data/eval_cases/heldout")

from src.agents.collector import CollectorAgent  # noqa: E402
from src.integrations.ryde_api import RydeAPIClient, load_dispute_dataset  # noqa: E402
from src.rag.qdrant_store import QdrantStore  # noqa: E402
from src.rag.query_builder import TYPE_HINTS, build_fact_query  # noqa: E402

POOL = 20
RRF_K = 60
WEIGHTS = (0.0, 0.0005, 0.001, 0.002, 0.004)
WRONG_TYPE_CYCLE = ("service_quality", "fare_dispute", "driver_rights")
OUT = ROOT / "data" / "eval" / "retrieval" / "fact_query.json"
ANSWER_KEYS = json.loads((ROOT / "data" / "eval_answer_keys.json").read_text(encoding="utf-8"))


def candidates(store, query: str) -> list[dict]:
    if not query:
        return []
    return [{"key": f"{p.payload.get('title')} > {p.payload.get('section')}",
             "types": set((p.payload.get("dispute_types") or "").split(",")) - {""}}
            for p in store.search_points(query, limit=POOL)]


def rank(lists: list[list[dict]], dtype: str, w: float) -> list[str]:
    score, info = {}, {}
    for lst in lists:
        for r, c in enumerate(lst):
            score[c["key"]] = score.get(c["key"], 0.0) + 1.0 / (RRF_K + r + 1)
            info[c["key"]] = c["types"]
    for key, types in info.items():
        tag = 1 if (dtype in types or "general" in types) else (-1 if types == {"none"} else 0)
        score[key] += w * tag
    return sorted(score, key=score.get, reverse=True)


def safe_rank(lst: list[dict], dtype: str, w: float, keep: int = 2, k: int = 5) -> list[str]:
    """Tag-ranked list whose top k always contains the plain search's top `keep`, so a
    misclassified case still sees the sections its own text matched best."""
    boosted, plain = rank([lst], dtype, w), rank([lst], dtype, 0.0)[:keep]
    head = [x for x in boosted if x not in plain][:k - len(plain)]
    head = sorted(head + plain, key=boosted.index)
    return head + [x for x in boosted if x not in head]


def metrics(ranked: list[str], gold: set[str]) -> dict:
    first = next((i for i, k in enumerate(ranked[:10]) if k in gold), None)
    return {"hit1": first == 0, "hit3": first is not None and first < 3,
            "hit5": first is not None and first < 5, "mrr": 0.0 if first is None else 1.0 / (first + 1)}


async def main():
    api = RydeAPIClient()
    api.list_orders()
    store = QdrantStore()
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
        dtype = getattr(ctx.type, "value", ctx.type) or exp.get("expected_dispute_type") or ""
        q_complaint = f"{ctx.description} {TYPE_HINTS.get(dtype, '')}".strip()
        q_facts = build_fact_query(ctx, dtype)
        c_list, f_list = candidates(store, q_complaint), candidates(store, q_facts)
        row = {"case": did, "set": "heldout" if exp.get("heldout") else "dev", "type": dtype,
               "facts_query": q_facts}
        for w in WEIGHTS:
            for name, lists in (("complaint", [c_list]), ("facts", [f_list or c_list]),
                                ("merged", [c_list, f_list] if f_list else [c_list])):
                row[f"{name}@w{w}"] = metrics(rank(lists, dtype, w), gold)
        # Misclassification check: the same search ranked toward a WRONG type must still
        # keep the right section near the top (tags rank, they must not hide a rule)
        wrong = next(t for t in WRONG_TYPE_CYCLE if t != dtype)
        for w in WEIGHTS:
            row[f"complaint_wrongtype@w{w}"] = metrics(rank([c_list], wrong, w), gold)
            row[f"safe@w{w}"] = metrics(safe_rank(c_list, dtype, w), gold)
            row[f"safe_wrongtype@w{w}"] = metrics(safe_rank(c_list, wrong, w), gold)
        rows.append(row)
        print(f"{did:<12} {dtype:<20} complaint top1 {rank([c_list], dtype, 0)[0][:55]}")

    variants = [k for k in rows[0] if "@w" in k]
    summary = {}
    for v in variants:
        for subset in ("all", "dev", "heldout"):
            rs = [r for r in rows if subset == "all" or r["set"] == subset]
            summary.setdefault(v, {})[subset] = {
                m: round(sum(float(r[v][m]) for r in rs) / len(rs), 3) for m in ("hit1", "hit3", "hit5", "mrr")}
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps({"summary": summary, "rows": rows}, indent=1, ensure_ascii=False), encoding="utf-8")
    print(f"\n{len(rows)} cases\n{'variant':<22} {'Hit@1':>6} {'Hit@3':>6} {'Hit@5':>6} {'MRR':>6}   (all cases)")
    for v in variants:
        s = summary[v]["all"]
        print(f"{v:<22} {s['hit1']:>6} {s['hit3']:>6} {s['hit5']:>6} {s['mrr']:>6}")
    print(f"\n{OUT}")


if __name__ == "__main__":
    asyncio.run(main())
