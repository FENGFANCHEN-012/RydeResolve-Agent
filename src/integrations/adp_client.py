"""Tencent ADP policy assistant for the human review desk.

The published ADP app (Hunyuan hy3, standard mode, knowledge base = the 22 official policy files)
answers over an SSE chat API. Only the backend calls it, so ADP_APP_KEY never reaches a browser.
ADP is the company's internal review tool, so the case summary may be sent with a question.
"""
import json
import os
import uuid

import httpx

from src import config  # noqa: F401  loads .env

# International site; ADP only answers in ap-jakarta for this account (scripts/adp/adp_chat_test.py)
DEFAULT_URL = "https://wss.lke.tencentcloud.com/v1/qbot/chat/sse"
_CASE_CHARS = 2500  # a long prompt dilutes ADP's document search, which keys on the whole content


class ADPError(RuntimeError):
    pass


def configured() -> bool:
    return bool(os.getenv("ADP_APP_KEY", "").strip())


def case_context(snapshot: dict, ruling: dict) -> str:
    """A compact case summary to put in front of a reviewer's question."""
    ctx = snapshot.get("context") or {}
    trip = ctx.get("trip") or {}
    lines = [
        f"Dispute {ctx.get('dispute_id') or ruling.get('dispute_id')} ({ctx.get('type') or ruling.get('dispute_type')}), "
        f"filed by the {ctx.get('reporter') or 'unknown party'}.",
        f"Complaint: {ctx.get('description') or ''}",
    ]
    keys = ("status", "cancellation_fee", "cleaning_fee", "total_fare", "estimated_fare", "cancel_reason",
            "driver_arrival_time", "cancelled_at", "pickup_time", "dropoff_time")
    facts = {k: trip[k] for k in keys if trip.get(k) is not None}
    if facts:
        lines.append("Trip record: " + json.dumps(facts, ensure_ascii=False))
    for f in (ctx.get("findings") or [])[:12]:
        if f.get("kind") in ("conflict", "gap", "fact"):
            lines.append(f"- {f['kind']}: {f.get('statement')}")
    if snapshot.get("response", {}).get("reason") or ruling.get("reason"):
        lines.append(f"Escalated because: {snapshot.get('response', {}).get('reason') or ruling.get('reason')}")
    return "\n".join(lines)[:_CASE_CHARS]


def _events(lines):
    """SSE events; one event's data may span several "data:" lines."""
    data: list[str] = []
    for raw in lines:
        if raw == "":
            if data:
                yield json.loads("\n".join(data))
                data = []
        elif raw.startswith("data:"):
            data.append(raw[5:].lstrip())
    if data:
        yield json.loads("\n".join(data))


async def ask(question: str, session_id: str | None = None, visitor: str = "ryderesolve-review") -> dict:
    """Ask the ADP app; returns {"answer", "references", "session_id"}. A reused session_id keeps
    ADP's conversation memory, so follow-up questions work."""
    key = os.getenv("ADP_APP_KEY", "").strip()
    if not key:
        raise ADPError("ADP is not configured (ADP_APP_KEY missing).")
    session_id = session_id or str(uuid.uuid4())
    body = {"content": question, "bot_app_key": key, "visitor_biz_id": visitor,
            "session_id": session_id, "streaming_throttle": 20}
    answer, refs = "", []
    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(120, connect=15)) as client:
            async with client.stream("POST", os.getenv("ADP_CHAT_URL", DEFAULT_URL), json=body) as resp:
                resp.raise_for_status()
                lines = [line async for line in resp.aiter_lines()]
    except httpx.HTTPError as exc:
        raise ADPError(f"ADP request failed: {exc.__class__.__name__}") from exc
    for event in _events(lines):
        payload = event.get("payload") or {}
        if event.get("type") == "reply" and not payload.get("is_from_self"):
            answer = payload.get("content", answer)  # each reply event carries the full text so far
        elif event.get("type") == "reference":
            refs += [r.get("name") or r.get("doc_name") or "" for r in payload.get("references") or []]
        elif event.get("type") == "error":
            raise ADPError("ADP returned an error: " + json.dumps(payload or event, ensure_ascii=False)[:200])
    return {"answer": answer, "references": sorted({r for r in refs if r}), "session_id": session_id}
