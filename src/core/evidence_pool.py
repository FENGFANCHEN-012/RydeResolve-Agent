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


class EvidencePool:
    """Helper to build, render and merge evidence-pool items."""

    @staticmethod
    def render_for_prompt(pool: list[EvidencePoolItem] | list[dict],
                          max_items: int = MAX_RENDERED_ITEMS) -> str:
        """The pool as a prompt section, newest items last."""
        if not pool:
            return ""
        lines = ["=== SHARED EVIDENCE POOL (lookups by either side, answered from platform records; "
                 "cite an item as [E#]) ==="]
        items = [i.model_dump() if isinstance(i, EvidencePoolItem) else i for i in pool]
        if len(items) > max_items:
            lines.append(f"(showing the last {max_items} of {len(items)} items)")
            items = items[-max_items:]
        for item in items:
            asked = f"asked by {item.get('source_agent')}, round {item.get('round', 0)}"
            lines.append(f"\n[{item.get('item_id')}] {item.get('description')} - {asked}"
                         + (f"; reason: {item['why']}" if item.get("why") else ""))
            for f in item.get("findings") or []:
                stmt = f.get("statement") if isinstance(f, dict) else str(f)
                kind = f.get("kind", "fact") if isinstance(f, dict) else "fact"
                lines.append(f"  - [{kind}] {stmt}")
        lines.append("=== END EVIDENCE POOL ===")
        return "\n".join(lines)

    @staticmethod
    def merge_pools(existing: list[dict], new_items: list[EvidencePoolItem]) -> list[dict]:
        """Append new items numbered E<n>. A lookup already in the pool (same tool and
        arguments) is not stored twice, whoever asked for it."""
        out = list(existing or [])
        seen = {_query_key(i) for i in out}
        for item in new_items:
            data = item.model_dump() if isinstance(item, EvidencePoolItem) else dict(item)
            key = _query_key(data)
            if key in seen:
                continue
            data["item_id"] = f"E{len(out) + 1}"
            out.append(data)
            seen.add(key)
        return out

    @staticmethod
    def ids(pool: list[dict] | None) -> set[str]:
        return {i.get("item_id") for i in pool or [] if isinstance(i, dict)}

    @staticmethod
    def unknown_refs(text: str, pool: list[dict] | None) -> list[str]:
        """[E#] references in a text that are not in the pool (a cited lookup that never happened)."""
        known = EvidencePool.ids(pool)
        return sorted({r for r in _EVIDENCE_REF.findall(text or "") if r not in known})
