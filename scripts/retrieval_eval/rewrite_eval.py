"""Does rewriting the query before retrieval help? An LLM turns each question
(especially raw complaint text) into a short policy search query; we then score
raw vs rewritten vs both (two searches fused by RRF) on the same test set.

Rewrites are cached in data/eval/retrieval/rewrites.json, so only the first run
spends LLM quota (one short call per question).

    LLM_PROVIDER=cerebras python scripts/retrieval_eval/rewrite_eval.py
"""
import asyncio
import json
import sys

from fastembed import SparseTextEmbedding, TextEmbedding

import common
import local_eval as le

sys.path.insert(0, str(common.ROOT))
from src.core.llm_client import LLMClient  # noqa: E402

CACHE = le.OUT / "rewrites.json"
PROMPT = """You turn a ride-hailing customer message into a search query for Ryde's help-centre policies.
Write ONE line (max 20 words): the policy topic(s) the message is about, who is asking (rider or driver),
and the key facts that decide which rule applies (times, amounts, what happened). Use plain policy words
(e.g. "cancellation fee", "no-show", "waiting time fee", "cleaning fee", "fixed fare", "fee waiver request").
Do not answer the question and do not invent rules. Output only the query line."""


async def rewrite_all(questions: list[dict]) -> dict[str, str]:
    cache = json.loads(CACHE.read_text(encoding="utf-8")) if CACHE.exists() else {}
    llm = LLMClient()
    for q in questions:
        if q["id"] in cache:
            continue
        text = await llm.chat([{"role": "system", "content": PROMPT}, {"role": "user", "content": q["query"]}],
                              temperature=0.0, max_tokens=800)
        cache[q["id"]] = text.strip().splitlines()[-1].strip().strip('"')
        print(f'{q["id"]}: {cache[q["id"]]}', flush=True)
        CACHE.write_text(json.dumps(cache, indent=1, ensure_ascii=False), encoding="utf-8")
    return cache


def fused_search(client, dense_model, sparse_model, queries: list[str]) -> list[int]:
    """Search each query, then merge the rankings with reciprocal-rank fusion."""
    scores: dict[int, float] = {}
    for query in queries:
        for rank, pid in enumerate(le.search(client, dense_model, sparse_model, query, "hybrid", le.TOP_K * 2)):
            scores[pid] = scores.get(pid, 0.0) + 1 / (60 + rank)
    return sorted(scores, key=lambda p: -scores[p])[:le.TOP_K]


def evaluate(name, questions, chunks, ranker) -> dict:
    rows = []
    for q in questions:
        ids = ranker(q)
        rel = [common.is_relevant(chunks[i]["stem"], chunks[i]["heading"], chunks[i]["text"], q["gold"]) for i in ids]
        rows.append({"id": q["id"], "style": q["style"], **common.score(rel)})
    out = {s: common.summarise([r for r in rows if s == "all" or r["style"] == s]) for s in ("all", "short", "complaint")}
    print(f"{name:<30}" + "  ".join(f"{s} Hit@1 {out[s]['hit1']:.2f} MRR {out[s]['mrr']:.3f}" for s in out))
    return {"name": name, "summary": out, "rows": rows}


def main():
    questions = common.load_questions()
    rewrites = asyncio.run(rewrite_all(questions))
    sparse_model = SparseTextEmbedding("Qdrant/bm25")
    chunks = le.build_chunks(with_title=False)
    results = []
    for dense_key in ("small", "base"):
        dense_model = TextEmbedding(le.DENSE[dense_key])
        client = le.build_index(chunks, dense_model, sparse_model)
        s = lambda qs: fused_search(client, dense_model, sparse_model, qs)  # noqa: E731
        tag = f"bge-{dense_key}"
        results.append(evaluate(f"{tag} raw", questions, chunks, lambda q: s([q["query"]])))
        results.append(evaluate(f"{tag} rewritten", questions, chunks, lambda q: s([rewrites[q["id"]]])))
        results.append(evaluate(f"{tag} raw+rewritten", questions, chunks, lambda q: s([q["query"], rewrites[q["id"]]])))
    (le.OUT / "rewrite.json").write_text(json.dumps(results, indent=1), encoding="utf-8")


if __name__ == "__main__":
    main()
