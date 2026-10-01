"""A/B the guarded LLM query rewrite (src/rag/guarded_rewrite.py, D13) on the live collection.

Two test sets, each searched with: raw text, the rewrite, and both fused (RRF):
  cases      the 27 eval cases (complaint + type hint), ranked with section tags as in the
             pipeline (TAG_WEIGHT); gold = expected_official_sections
  questions  the 32 retrieval questions (scripts/retrieval_eval/eval_set.json), no type, so no
             tag ranking; reported for 'short' and 'complaint' style separately
A rejected rewrite (guard) falls back to the raw text, exactly as the pipeline would.
Rewrites are cached in data/eval/retrieval/rewrites_guarded.json: only the first run calls the LLM.

    LLM_PROVIDER=cerebras python scripts/retrieval_eval/rewrite_guarded_eval.py
"""
import asyncio
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).parent))
os.environ.setdefault("EXTRA_DISPUTE_DIRS", "data/eval_cases/heldout")

import common  # noqa: E402
from src.core.llm_client import LLMClient  # noqa: E402
from src.integrations.ryde_api import RydeAPIClient, load_dispute_dataset  # noqa: E402
from src.rag.qdrant_store import QdrantStore  # noqa: E402
from src.rag.query_builder import TYPE_HINTS  # noqa: E402
from src.rag.guarded_rewrite import rewrite_query  # noqa: E402
from src.rag.retriever import CANDIDATE_POOL, TAG_WEIGHT, rank_by_tags  # noqa: E402

OUT = ROOT / "data" / "eval" / "retrieval"
CACHE = OUT / "rewrites_guarded.json"
ANSWER_KEYS = json.loads((ROOT / "data" / "eval_answer_keys.json").read_text(encoding="utf-8"))


def search(store, query: str) -> list[dict]:
    return [{"source": p.payload.get("source", ""), "title": p.payload.get("title"),
             "section": p.payload.get("section", ""), "text": p.payload.get("text", ""),
             "dispute_types": p.payload.get("dispute_types", "")}
            for p in store.search_points(query, limit=CANDIDATE_POOL)]


def fuse(lists: list[list[dict]]) -> list[dict]:
    score, keep = {}, {}
    for lst in lists:
        for r, c in enumerate(lst):
            key = (c["title"], c["section"], c["text"][:80])
            score[key] = score.get(key, 0.0) + 1.0 / (60 + r + 1)
            keep[key] = c
    return [keep[k] for k in sorted(score, key=score.get, reverse=True)]


def first_hit(ranked: list[bool]) -> dict:
    first = next((i for i, ok in enumerate(ranked[:10]) if ok), None)
    return {"hit1": first == 0, "hit3": first is not None and first < 3,
            "mrr": 0.0 if first is None else 1.0 / (first + 1)}


def avg(rows, key):
    return {m: round(sum(float(r[key][m]) for r in rows) / len(rows), 3) for m in ("hit1", "hit3", "mrr")} if rows else {}


async def rewrites_for(items: dict[str, str]) -> dict[str, dict]:
    cache = json.loads(CACHE.read_text(encoding="utf-8")) if CACHE.exists() else {}
    llm = None
    for key, text in items.items():
        if key in cache:
            continue
        llm = llm or LLMClient()
        query, note = await rewrite_query(text, llm)
        cache[key] = {"source": text, "rewrite": query, "note": note}
        print(f"{key}: {note} | {query}", flush=True)
        OUT.mkdir(parents=True, exist_ok=True)
        CACHE.write_text(json.dumps(cache, indent=1, ensure_ascii=False), encoding="utf-8")
    return cache


async def main():
    api = RydeAPIClient()
    api.list_orders()
    cases = []
    for order_id, path in sorted(api._index.items()):
        data = load_dispute_dataset(path)
        ticket = data.get("dispute_ticket") or {}
        did = ticket.get("dispute_id") or order_id
        exp = data.get("expected_outcome") or ANSWER_KEYS.get(did) or {}
        if exp.get("expected_official_sections"):
            cases.append((did, ticket.get("description", ""), exp))
    questions = common.load_questions()

    items = {f"case:{did}": desc for did, desc, _ in cases}
    items.update({f"q:{q['id']}": q["query"] for q in questions})
    rw = await rewrites_for(items)
    rejected = [k for k, v in rw.items() if k in items and v["rewrite"] is None]

    store = QdrantStore()
    case_rows = []
    for did, desc, exp in cases:
        dtype = exp.get("expected_dispute_type") or ""
        gold = set(exp["expected_official_sections"])
        hint = TYPE_HINTS.get(dtype, "")
        raw = search(store, f"{desc} {hint}".strip())
        rew_text = rw[f"case:{did}"]["rewrite"]
        rew = search(store, f"{rew_text} {hint}".strip()) if rew_text else raw
        row = {"case": did}
        for name, lst in (("raw", raw), ("rewrite", rew), ("both", fuse([raw, rew]))):
            ranked = rank_by_tags(lst, dtype, TAG_WEIGHT)
            row[name] = first_hit([f"{c['title']} > {c['section']}" in gold for c in ranked])
        case_rows.append(row)

    q_rows = []
    for q in questions:
        raw = search(store, q["query"])
        rew_text = rw[f"q:{q['id']}"]["rewrite"]
        rew = search(store, rew_text) if rew_text else raw
        row = {"id": q["id"], "style": q["style"]}
        for name, lst in (("raw", raw), ("rewrite", rew), ("both", fuse([raw, rew]))):
            rel = [common.is_relevant(c["source"].removesuffix(".md"), c["section"], c["text"], q["gold"])
                   for c in lst]
            row[name] = first_hit(rel)
        q_rows.append(row)

    summary = {"rejected_rewrites": rejected}
    print(f"\nRewrites rejected by the guard: {len(rejected)} {rejected}")
    print(f"{'set':<22} {'variant':<8} {'Hit@1':>6} {'Hit@3':>6} {'MRR':>6}")
    for label, rows in (("27 cases (+tags)", case_rows),
                        ("questions: short", [r for r in q_rows if r["style"] == "short"]),
                        ("questions: complaint", [r for r in q_rows if r["style"] == "complaint"])):
        for v in ("raw", "rewrite", "both"):
            s = avg(rows, v)
            summary.setdefault(label, {})[v] = s
            print(f"{label:<22} {v:<8} {s['hit1']:>6} {s['hit3']:>6} {s['mrr']:>6}")
    (OUT / "rewrite_guarded.json").write_text(
        json.dumps({"summary": summary, "cases": case_rows, "questions": q_rows}, indent=1), encoding="utf-8")


if __name__ == "__main__":
    asyncio.run(main())
