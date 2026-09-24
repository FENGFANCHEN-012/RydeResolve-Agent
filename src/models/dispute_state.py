"""
Shared cross-agent dispute state models.

These Pydantic models capture the inputs that flow between agents in the
RydeResolve dispute-resolution pipeline. They are intentionally serialisable
so they can later back a LangGraph ``TypedDict`` state without forcing the
agent modules themselves to depend on LangGraph.

Only models that span multiple agents belong here (e.g. the Fairness Agent's
assessment input, which reads outputs from the Collector, Classifier,
DebateEngine, Policy Agent and Arbitrator). Agent-local models (Decision,
ClassificationResult, etc.) stay inside their own agent modules.
"""
from pydantic import BaseModel, ConfigDict

from src.agents.arbitrator import Decision


class FairnessAssessmentInput(BaseModel):
    """
    Frozen, auditable input to the Fairness Agent.

    Produced by the orchestrator (or future LangGraph graph) right after the
    Arbitrator produces its ``Decision``. Read-only by construction so the
    Fairness Agent can never mutate upstream state.

    Attributes:
        dispute_id: Unique dispute identifier (e.g. ``"DRP-ORDER123"``).
        decision: Arbitrator's ``Decision``.
        passenger_analysis: Output of ``PassengerAgent.analyze`` (dict).
        driver_analysis: Output of ``DriverAgent.analyze`` (dict).
        policy_evaluation: Output of ``PolicyAgent.evaluate_compliance``.
            May also contain the RAG-retrieved clauses under any of the keys
            ``"policies"``, ``"chunks"`` or ``"clauses"`` (arbitrator-style).
        debate_history: Full ``DebateEngine.debate`` history (each entry is a
            ``{"round": int, "speaker": str, "content": dict | str}``).
        context: ``DisputeContext.model_dump()``. Used only for evidence
            counts (chat log length, GPS points, evidence items). The
            Fairness Agent must NEVER base its judgment on protected or
            demographic fields.
    """

    model_config = ConfigDict(frozen=True, arbitrary_types_allowed=True)

    dispute_id: str
    decision: Decision
    passenger_analysis: dict
    driver_analysis: dict
    policy_evaluation: dict
    debate_history: list[dict]
    context: dict
