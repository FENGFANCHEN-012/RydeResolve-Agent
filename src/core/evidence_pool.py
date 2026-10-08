"""
Shared Evidence Pool for the multi-agent dispute resolution system.

Every agent can deposit findings into the pool, and every other agent can read
from it.  This guarantees that:
- a lookup by the passenger advocate is visible to the driver advocate,
- both sides' lookups are visible to the Judge and the Fairness agent,
- no agent can claim exclusive knowledge of a fact.

Items are numbered E1, E2, ... in the order they enter the pool, so arguments and
rulings can cite them ("[E3]") and the citations can be checked in code.
Only the system writes items: an agent asks for a lookup, a deterministic Collector
tool answers it, and the answer is stored. Agents never write facts themselves.

The pool is attached to the DisputeContext and flows through the workflow.
"""
from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from typing import Any

from pydantic import BaseModel

from src.agents.collector_tools import Finding

# Items shown in a prompt; older ones stay in the pool for audit and replay
MAX_RENDERED_ITEMS = 12
# Newest items shown in full to the advocates; older ones as one line of this many characters
FULL_RECENT_ITEMS = 4
SHORT_ITEM_CHARS = 160
_EVIDENCE_REF = re.compile(r"\bE\d+\b")


class EvidencePoolItem(BaseModel):
    """One entry in the shared evidence pool."""

    item_id: str = ""          # E1, E2, ... assigned when the item joins the pool
    source_agent: str          # "passenger" | "driver" | "system"
    item_type: str             # "collector_tool"
    description: str           # human-readable summary of what was queried
    query: dict[str, Any]      # the query parameters (tool name + args)
    findings: list[dict] = []  # serialized Finding objects
    round: int = 0             # debate round the lookup was made in (0 = opening)
    why: str = ""              # the asking agent's stated reason
    shared: bool = True        # always True; every side sees every item
    timestamp: str

    @classmethod
    def from_collector_tool(
        cls,
        source_agent: str,
        tool_name: str,
        params: dict[str, Any],
        findings: list[Finding],
        round: int = 0,
        why: str = "",
    ) -> "EvidencePoolItem":
        return cls(
            source_agent=source_agent,
            item_type="collector_tool",
            description=f"{source_agent} looked up '{tool_name}'"
                        + (f" ({', '.join(f'{k}={v}' for k, v in params.items())})" if params else ""),
            query={"tool": tool_name, **params},
            findings=[f.model_dump() for f in findings],
            round=round,
            why=why,
            timestamp=datetime.now(timezone.utc).isoformat(),
        )


def _query_key(item: dict) -> str:
    return json.dumps(item.get("query") or {}, sort_keys=True, default=str)


def _content_key(item: dict) -> str | None:
    """The records a lookup returned (tool + sources). Two windows a few seconds apart that
    return the same events are the same evidence (D24 step 3b: FD-002 stored one window 3 times)."""
    sources = sorted({s for f in item.get("findings") or [] if isinstance(f, dict) for s in f.get("sources") or []})
    if not sources:
        return None
    return (item.get("query") or {}).get("tool", "") + "|" + ",".join(sources)


class EvidencePool:
    """Helper to build, render and merge evidence-pool items."""

    @staticmethod
    def render_for_prompt(pool: list[EvidencePoolItem] | list[dict],
                          max_items: int = MAX_RENDERED_ITEMS,
                          full_last: int | None = FULL_RECENT_ITEMS) -> str:
        """The pool as a prompt section, newest items last. Only the newest `full_last` items are
        shown in full; older ones as one line each, since the agent has read them on an earlier
        turn (D24 token diet). full_last=None shows every item in full (the Judge)."""
        if not pool:
            return ""
        lines = ["=== SHARED EVIDENCE POOL (lookups by either side, answered from platform records; "
                 "cite an item as [E#]) ==="]
        items = [i.model_dump() if isinstance(i, EvidencePoolItem) else i for i in pool]
        if len(items) > max_items:
            lines.append(f"(showing the last {max_items} of {len(items)} items)")
            items = items[-max_items:]
        first_full = 0 if full_last is None else max(0, len(items) - full_last)
        for n, item in enumerate(items):
            statements = [(f.get("kind", "fact"), f.get("statement")) if isinstance(f, dict) else ("fact", str(f))
                          for f in item.get("findings") or []]
            if n < first_full:
                short = " ".join(" ".join(str(s) for _, s in statements).split())[:SHORT_ITEM_CHARS]
                lines.append(f"[{item.get('item_id')}] ({item.get('source_agent')}) {short}")
                continue
            asked = f"asked by {item.get('source_agent')}, round {item.get('round', 0)}"
            lines.append(f"\n[{item.get('item_id')}] {item.get('description')} - {asked}"
                         + (f"; reason: {item['why']}" if item.get("why") else ""))
            lines.extend(f"  - [{kind}] {stmt}" for kind, stmt in statements)
        lines.append("=== END EVIDENCE POOL ===")
        return "\n".join(lines)

    @staticmethod
    def merge_pools(existing: list[dict], new_items: list[EvidencePoolItem]) -> list[dict]:
        """Append new items numbered E<n>. A lookup already in the pool (same tool and
        arguments) is not stored twice, whoever asked for it."""
        out = list(existing or [])
        seen = {_query_key(i) for i in out} | {k for k in map(_content_key, out) if k}
        for item in new_items:
            data = item.model_dump() if isinstance(item, EvidencePoolItem) else dict(item)
            keys = {_query_key(data), _content_key(data)} - {None}
            if keys & seen:
                continue   # same lookup, or a different lookup that returned the same records
            data["item_id"] = f"E{len(out) + 1}"
            out.append(data)
            seen |= keys
        return out

    @staticmethod
    def ids(pool: list[dict] | None) -> set[str]:
        return {i.get("item_id") for i in pool or [] if isinstance(i, dict)}

    @staticmethod
    def unknown_refs(text: str, pool: list[dict] | None) -> list[str]:
        """[E#] references in a text that are not in the pool (a cited lookup that never happened)."""
        known = EvidencePool.ids(pool)
        return sorted({r for r in _EVIDENCE_REF.findall(text or "") if r not in known})
