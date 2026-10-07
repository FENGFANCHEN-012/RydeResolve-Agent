"""
Shared Evidence Pool for the multi-agent dispute resolution system.

Every agent can deposit findings into the pool, and every other agent can read
from it.  This guarantees that:
- an auto-query by the passenger advocate is visible to the driver advocate,
- both sides' queries are visible to the Judge and the Fairness agent,
- no agent can claim exclusive knowledge of a fact.

The pool is attached to the DisputeContext and flows through the workflow.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

from pydantic import BaseModel

from src.agents.collector_tools import Finding


class EvidencePoolItem(BaseModel):
    """One entry in the shared evidence pool."""

    item_id: str
    source_agent: str          # "passenger" | "driver" | "collector" | "policy" | "system"
    item_type: str             # "collector_tool" | "rag_policy" | "platform_data" | "requested_policy"
    description: str           # human-readable summary of what was queried
    query: dict[str, Any]      # the query parameters (tool name + args, or search text)
    findings: list[dict] = []  # serialized Finding objects or clause dicts
    shared: bool = True        # always True for now; reserved for future selective sharing
    timestamp: str

    @classmethod
    def from_collector_tool(
        cls,
        source_agent: str,
        tool_name: str,
        params: dict[str, Any],
        findings: list[Finding],
    ) -> "EvidencePoolItem":
        return cls(
            item_id=f"ep-{uuid.uuid4().hex[:8]}",
            source_agent=source_agent,
            item_type="collector_tool",
            description=f"{source_agent} auto-queried collector tool '{tool_name}'",
            query={"tool": tool_name, **params},
            findings=[f.model_dump() for f in findings],
            timestamp=datetime.now(timezone.utc).isoformat(),
        )

    @classmethod
    def from_rag_policy(
        cls,
        source_agent: str,
        topic: str,
        clauses: list[dict],
    ) -> "EvidencePoolItem":
        return cls(
            item_id=f"ep-{uuid.uuid4().hex[:8]}",
            source_agent=source_agent,
            item_type="rag_policy",
            description=f"{source_agent} retrieved policy topic '{topic}'",
            query={"topic": topic},
            findings=clauses,
            timestamp=datetime.now(timezone.utc).isoformat(),
        )


class EvidencePool:
    """Helper to build, render and merge evidence-pool items."""

    @staticmethod
    def render_for_prompt(pool: list[EvidencePoolItem] | list[dict], max_items: int = 5) -> str:
        """Render the pool as a compact prompt section. Only the most recent `max_items` are
        included to keep the Judge prompt small; earlier items are still in the pool for
        audit and replay."""
        if not pool:
            return ""
        lines = ["=== SHARED EVIDENCE POOL (auto-queries visible to all agents) ==="]
        items = list(pool)
        if len(items) > max_items:
            lines.append(f"(showing last {max_items} of {len(items)} items)")
            items = items[-max_items:]
        for item in items:
            if isinstance(item, EvidencePoolItem):
                item = item.model_dump()
            lines.append(f"\n[{item.get('item_id')}] {item.get('source_agent')} -> {item.get('item_type')}")
            lines.append(f"  Query: {item.get('description')}")
            for f in item.get("findings") or []:
                stmt = f.get("statement") if isinstance(f, dict) else str(f)
                kind = f.get("kind", "fact") if isinstance(f, dict) else "fact"
                lines.append(f"  - [{kind}] {stmt}")
        lines.append("=== END EVIDENCE POOL ===")
        return "\n".join(lines)

    @staticmethod
    def merge_pools(existing: list[dict], new_items: list[EvidencePoolItem]) -> list[dict]:
        """Append new items, deduplicating by item_id."""
        seen = {i.get("item_id") for i in existing}
        out = list(existing)
        for item in new_items:
            if item.item_id not in seen:
                out.append(item.model_dump())
                seen.add(item.item_id)
        return out
