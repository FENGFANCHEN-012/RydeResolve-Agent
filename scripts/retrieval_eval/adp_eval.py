"""Score Tencent ADP's retrieval on the same questions. Each question is sent to
the published app over the SSE chat API; the token_stat event carries the
passages the knowledge step actually retrieved (in rank order), which are
scored exactly like the local chunks. One chat call per question.

    python scripts/retrieval_eval/adp_eval.py  ->  data/eval/retrieval/adp.json
"""
import json
import re
import sys
import time
import uuid

import requests

import common

sys.path.insert(0, str(common.ROOT / "scripts" / "adp"))
from adp_common import ENV  # noqa: E402  (reads .env, never prints the key)

KEY = ENV["ADP_APP_KEY"].strip()
ENDPOINT = "https://wss.lke.tencentcloud.com/v1/qbot/chat/sse"
OUT = common.ROOT / "data" / "eval" / "retrieval"


def ask(question: str) -> tuple[list[dict], str, float]:
    """Return (retrieved passages in rank order, final answer, seconds until the
    knowledge step finished)."""
    body = {"content": question, "bot_app_key": KEY, "visitor_biz_id": "retrieval-eval",
            "session_id": str(uuid.uuid4()), "streaming_throttle": 50}
    passages, answer, retrieval_s, steps = [], "", None, set()
    t0 = time.perf_counter()
    with requests.post(ENDPOINT, json=body, stream=True, timeout=180) as resp:
        resp.raise_for_status()
        resp.encoding = "utf-8"
        data = []
        for line in resp.iter_lines(decode_unicode=True):
            if line.startswith("data:"):
                data.append(line[5:].lstrip())
                continue
            if line != "" or not data:
                continue
            event = json.loads("\n".join(data))
            data = []
            payload = event.get("payload") or {}
            if event.get("type") == "token_stat":
                for proc in payload.get("procedures") or []:
                    steps.add(f'{proc.get("name")}/{(proc.get("debugging") or {}).get("intent_cate", "")}')
                    found = (proc.get("debugging") or {}).get("knowledge")
                    if found and not passages:
                        passages, retrieval_s = found, time.perf_counter() - t0
                if passages:
                    break  # retrieval is all we score; stop before the answer streams
            elif event.get("type") == "reply" and not payload.get("is_from_self"):
                answer = payload.get("content", answer)
            elif event.get("type") == "error":
                raise RuntimeError(json.dumps(event, ensure_ascii=False)[:300])
    return passages, sorted(steps), retrieval_s or 0.0


def ask_retry(question: str, tries: int = 3):
    for attempt in range(tries):
        try:
            return ask(question)
        except (requests.ConnectionError, requests.exceptions.ChunkedEncodingError) as exc:
            if attempt == tries - 1:
                raise
            print(f"  connection dropped ({type(exc).__name__}), retrying", flush=True)
            time.sleep(5)


def parse(passage: dict) -> tuple[str, str, str]:
    """ADP passage text -> (file stem, section heading or "", body)."""
    text = passage.get("content", "")
    m = re.match(r"File name:\s*(\S+)", text)
    stem = m.group(1).removesuffix(".md") if m else ""
    h = re.search(r"^## (.+)$", text, re.M)
    body = text.split("Passage:", 1)[-1]
    return stem, h.group(1).strip() if h else "", body


def main():
    rows = []
    for q in common.load_questions():
        passages, steps, secs = ask_retry(q["query"])
        parsed = [parse(p) for p in passages]
        rel = [common.is_relevant(stem, head, body, q["gold"]) for stem, head, body in parsed]
        rows.append({
            "id": q["id"], "style": q["style"], "ms": round(secs * 1000), "n_passages": len(parsed),
            "mojibake": sum("�" in body for _, _, body in parsed), **common.score(rel),
            "top3": [f"{s} :: {h}" for s, h, _ in parsed[:3]], "steps": steps,
            "passages": [p.get("content", "") for p in passages],
        })
        r = rows[-1]
        print(f'{q["id"]} first relevant rank={r["first_rank"]} passages={r["n_passages"]} {secs:.1f}s', flush=True)
    summary = {"all": common.summarise(rows),
               "short": common.summarise([r for r in rows if r["style"] == "short"]),
               "complaint": common.summarise([r for r in rows if r["style"] == "complaint"]),
               "avg_ms": round(sum(r["ms"] for r in rows) / len(rows))}
    a = summary["all"]
    print(f"ADP  Hit@1 {a['hit1']:.2f}  Hit@3 {a['hit3']:.2f}  Hit@8 {a['hit8']:.2f}  MRR {a['mrr']:.3f}  "
          f"{summary['avg_ms']} ms/q to retrieval")
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "adp.json").write_text(json.dumps({"name": "ADP", "summary": summary, "rows": rows}, indent=1,
                                             ensure_ascii=False), encoding="utf-8")


if __name__ == "__main__":
    main()
