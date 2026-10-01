"""Score our local hybrid retrieval on the official policies, in an in-memory
Qdrant (the cloud collection is never touched). Runs the live configuration
plus a few candidate improvements so they can be compared on the same questions.

    python scripts/retrieval_eval/local_eval.py  ->  data/eval/retrieval/local.json
"""
import json
import sys
import time
from pathlib import Path

from fastembed import SparseTextEmbedding, TextEmbedding
from fastembed.rerank.cross_encoder import TextCrossEncoder
from qdrant_client import QdrantClient, models

import common

sys.path.insert(0, str(common.ROOT))
from src.rag.indexer import DocumentIndexer  # noqa: E402

TOP_K = 8          # same as ADP's DocTopN
RERANK_POOL = 20   # candidates handed to the reranker
DENSE = {"small": "BAAI/bge-small-en-v1.5", "base": "BAAI/bge-base-en-v1.5"}
RERANKERS = {"jina-turbo": "jinaai/jina-reranker-v1-turbo-en", "bge-reranker": "BAAI/bge-reranker-base"}
OUT = common.ROOT / "data" / "eval" / "retrieval"


def build_chunks(with_title: bool) -> list[dict]:
    """Chunk the official files exactly like the live indexer ("## " sections)."""
    chunker = DocumentIndexer.__new__(DocumentIndexer)  # chunking needs no store
    chunks = []
    for f in sorted(common.OFFICIAL.glob("*.md")):
        if f.name == "README.md":
            continue
        text = f.read_text(encoding="utf-8")
        title = text.split("\n", 1)[0].lstrip("# ").strip()
        for i, (heading, body) in enumerate(chunker._chunk_markdown(text)):
            embed_text = f"{title} | {heading}\n{body}" if with_title and heading != "Overview" else body
            chunks.append({"id": len(chunks), "stem": f.stem, "heading": heading, "text": body, "embed_text": embed_text})
    return chunks


def build_index(chunks: list[dict], dense_model: TextEmbedding, sparse_model: SparseTextEmbedding) -> QdrantClient:
    client = QdrantClient(":memory:")
    texts = [c["embed_text"] for c in chunks]
    dense_vecs = list(dense_model.embed(texts))
    client.create_collection(
        "eval",
        vectors_config={"dense": models.VectorParams(size=len(dense_vecs[0]), distance=models.Distance.COSINE)},
        sparse_vectors_config={"sparse": models.SparseVectorParams(modifier=models.Modifier.IDF)},
    )
    client.upload_points("eval", points=[
        models.PointStruct(
            id=c["id"],
            vector={"dense": d.tolist(), "sparse": models.SparseVector(indices=s.indices.tolist(), values=s.values.tolist())},
            payload={},
        )
        for c, d, s in zip(chunks, dense_vecs, sparse_model.embed(texts))
    ])
    return client


def search(client, dense_model, sparse_model, query: str, mode: str, limit: int) -> list[int]:
    """mode: hybrid (live: dense + BM25, RRF, prefetch 4x), dense, or bm25."""
    q_dense = next(iter(dense_model.query_embed(query))).tolist()
    q_sparse = next(iter(sparse_model.query_embed(query)))
    sparse_q = models.SparseVector(indices=q_sparse.indices.tolist(), values=q_sparse.values.tolist())
    if mode == "dense":
        res = client.query_points("eval", query=q_dense, using="dense", limit=limit)
    elif mode == "bm25":
        res = client.query_points("eval", query=sparse_q, using="sparse", limit=limit)
    else:
        res = client.query_points(
            "eval",
            prefetch=[
                models.Prefetch(query=q_dense, using="dense", limit=limit * 4),
                models.Prefetch(query=sparse_q, using="sparse", limit=limit * 4),
            ],
            query=models.FusionQuery(fusion=models.Fusion.RRF),
            limit=limit,
        )
    return [p.id for p in res.points]


def run_variant(name, questions, chunks, client, dense_model, sparse_model, mode="hybrid", reranker=None):
    rows = []
    if reranker:
        list(reranker.rerank("warm up", ["first call loads the model"]))  # keep load time out of ms/q
    for q in questions:
        t0 = time.perf_counter()
        ids = search(client, dense_model, sparse_model, q["query"], mode, RERANK_POOL if reranker else TOP_K)
        if reranker:
            scores = list(reranker.rerank(q["query"], [chunks[i]["embed_text"] for i in ids]))
            ids = [i for _, i in sorted(zip(scores, ids), key=lambda x: -x[0])]
        ids = ids[:TOP_K]
        ms = (time.perf_counter() - t0) * 1000
        rel = [common.is_relevant(chunks[i]["stem"], chunks[i]["heading"], chunks[i]["text"], q["gold"]) for i in ids]
        rows.append({
            "id": q["id"], "style": q["style"], "ms": round(ms, 1), **common.score(rel),
            "top3": [f'{chunks[i]["stem"]} :: {chunks[i]["heading"]}' for i in ids[:3]],
        })
    summary = {"all": common.summarise(rows),
               "short": common.summarise([r for r in rows if r["style"] == "short"]),
               "complaint": common.summarise([r for r in rows if r["style"] == "complaint"]),
               "avg_ms": round(sum(r["ms"] for r in rows) / len(rows), 1)}
    a = summary["all"]
    print(f"{name:<34} Hit@1 {a['hit1']:.2f}  Hit@3 {a['hit3']:.2f}  Hit@8 {a['hit8']:.2f}  MRR {a['mrr']:.3f}  "
          f"{summary['avg_ms']:>6.1f} ms/q")
    return {"name": name, "summary": summary, "rows": rows}


def main():
    questions = common.load_questions()
    sparse_model = SparseTextEmbedding("Qdrant/bm25")
    rerankers = {k: TextCrossEncoder(v) for k, v in RERANKERS.items()}
    results = []
    for dense_key in ("small", "base"):
        dense_model = TextEmbedding(DENSE[dense_key])
        for with_title in (False, True):
            chunks = build_chunks(with_title)
            client = build_index(chunks, dense_model, sparse_model)
            tag = f"bge-{dense_key}{' +title' if with_title else ''}"
            if dense_key == "small" and not with_title:
                print(f"{len(chunks)} chunks indexed")
                results.append(run_variant(f"{tag} dense only", questions, chunks, client, dense_model, sparse_model, "dense"))
                results.append(run_variant(f"{tag} BM25 only", questions, chunks, client, dense_model, sparse_model, "bm25"))
            results.append(run_variant(f"{tag} hybrid", questions, chunks, client, dense_model, sparse_model))
            for rk, rr in rerankers.items():
                results.append(run_variant(f"{tag} hybrid +{rk}", questions, chunks, client, dense_model, sparse_model, reranker=rr))
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "local.json").write_text(json.dumps(results, indent=1), encoding="utf-8")


if __name__ == "__main__":
    main()
