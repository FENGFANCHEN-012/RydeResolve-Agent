"""
Shared LangGraph workflow state for the dispute-resolution pipeline.

This is the single state schema that flows through every node of the
LangGraph graph defined in ``src/core/workflow.py``.

Design notes:
- It is a plain ``TypedDict`` (total=False) so LangGraph treats every key
  as an independent "last value wins" channel; nodes return *partial*
  updates and never mutate shared state in place.
- Values may be Pydantic models (``DisputeContext``, ``ClassificationResult``,
  ``Decision``, ``FairnessAssessment``). They are passed by reference between
  nodes, which is fine without a checkpointer. If persistence is added
  later, nodes should ``model_dump()`` these values first.
- Control keys (``status``, ``human_review_reason``, ``error``) are what the
  conditional edges route on.
"""
from __future__ import annotations

from typing import TypedDict

from src.agents.arbitrator import Decision
from src.agents.classifier import ClassificationResult
from src.agents.collector import DisputeContext, EvidenceItem
from src.agents.fairness import FairnessAssessment

# Status values used across the workflow / orchestrator response.
STATUS_IN_PROGRESS = "in_progress"
STATUS_RESOLVED = "resolved"
STATUS_ESCALATED = "escalated_to_human"   # matches the legacy orchestrator string
STATUS_FAILED = "failed"


class DisputeWorkflowState(TypedDict, total=False):
    """State shared by all nodes in the dispute-resolution graph."""

    # --- Request (set once at entry by the Orchestrator) --------------
    report_text: str
    order_id: str
    reporter: str                       # "passenger" | "driver"
    evidence: list[EvidenceItem]
    language: str                       # en, zh, ms, ta

    # --- Pipeline artifacts (one producer each) -----------------------
    context: DisputeContext             # collector node
    classification: ClassificationResult  # classifier node
    fraud_report: dict                  # fraud node: risk report for the Judge and Fairness only
    triage: dict                        # debate node: complexity x risk, rounds, audit depth (D24)
    safety: dict                        # safety node: tier, actions, human review now/after (D24)
    debate_history: list[dict]          # debate node
    decision: Decision                  # arbitrator node
    precedents: list[dict]              # arbitrator node: human-reviewed precedents shown to the Judge
    fairness: FairnessAssessment        # fairness node
    fairness_remands: int               # arbitrator node: times Fairness sent the ruling back (D27)
    execution: dict                     # executor node

    # --- Control / audit ----------------------------------------------
    status: str                         # one of the STATUS_* constants
    human_review_reason: str | None     # why the case left the automated path
    error: dict | None                  # {"node": str, "type": str, "message": str}
