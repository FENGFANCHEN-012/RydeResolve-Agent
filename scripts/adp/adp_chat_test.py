"""Ask the published ADP app a few questions over its HTTP SSE chat API and print the
final answers plus cited documents. The app key is read from .env and never printed."""
import json
import sys
import uuid

import requests

from adp_common import ENV

KEY = ENV["ADP_APP_KEY"].strip()
ENDPOINTS = [
    "https://wss.lke.tencentcloud.com/v1/qbot/chat/sse",   # international site
    "https://wss.lke.cloud.tencent.com/v1/qbot/chat/sse",  # China site
]
QUESTIONS = sys.argv[1:] or [
    "How much is the cancellation fee if I cancel an on-demand ride after 3 minutes?",
    "When can a driver charge a no-show fee?",
    "What evidence does a driver need for a vomit cleaning claim, and what is the maximum?",
    "Does Ryde give a free cancellation if the driver is more than 10 minutes late?",
]


def sse_events(resp):
    """Yield each SSE event's JSON; an event's data can span several "data:" lines."""
    data: list[str] = []
    for raw in resp.iter_lines(decode_unicode=True):
        if raw is None:
            continue
        if raw == "":
            if data:
                yield json.loads("\n".join(data))
                data = []
        elif raw.startswith("data:"):
            data.append(raw[5:].lstrip())
    if data:
        yield json.loads("\n".join(data))


def ask(endpoint: str, question: str) -> tuple[str, list[str]]:
    body = {
        "content": question,
        "bot_app_key": KEY,
        "visitor_biz_id": "rydereresolve-test",
        "session_id": str(uuid.uuid4()),
        "streaming_throttle": 20,
    }
    answer, refs = "", []
    with requests.post(endpoint, json=body, stream=True, timeout=120) as resp:
        resp.raise_for_status()
        resp.encoding = "utf-8"
        for event in sse_events(resp):
            payload = event.get("payload") or {}
            if event.get("type") == "reply" and not payload.get("is_from_self"):
                answer = payload.get("content", answer)
            elif event.get("type") == "reference":
                refs += [r.get("name") or r.get("doc_name") or "" for r in payload.get("references") or []]
            elif event.get("type") == "error":
                raise RuntimeError(json.dumps(event, ensure_ascii=False)[:300])
    return answer, refs


endpoint = None
for candidate in ENDPOINTS:
    try:
        ask(candidate, "hello")
        endpoint = candidate
        break
    except Exception as exc:  # try the next site
        print(f"endpoint {candidate} failed: {str(exc)[:150]}")
if not endpoint:
    raise SystemExit("no chat endpoint worked")
print(f"using {endpoint}\n")
for q in QUESTIONS:
    answer, refs = ask(endpoint, q)
    print(f"Q: {q}\nA: {answer.strip()[:900]}\nsources: {sorted(set(r for r in refs if r))}\n")
