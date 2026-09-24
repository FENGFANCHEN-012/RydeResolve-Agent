"""
LangGraph workflow for the RydeResolve dispute-resolution pipeline.

Graph topology::

    START
      -> collector
      -> classifier
      -> [route_after_classifier]
             requires_human or node error -> human_review -> END
             otherwise                     -> debate
      -> debate
      -> [route_after_error]  -> arbitrator (or human_review on failure)
      -> arbitrator
      -> [route_after_error]  -> fairness  (or human_review on failure)
      -> fairness
      -> [route_after_fairness]
             arbitrator requests review, requires_human_review=True, or recommendation is
             AMEND_RECOMMENDED / ESCALATE / BLOCK, or node error
                                            -> human_review -> END
             PROCEED                        -> executor
      -> executor -> END (resolved only when execution succeeds)

Design principles:
- **Reuse, don't rewrite**: every node is a thin async adapter around the
  existing agents' public methods (``CollectorAgent.collect``,
  ``ClassifierAgent.classify``, ``DebateEngine.debate``,
  ``ArbitrationAgent.arbitrate``, ``FairnessAgent.assess``,
  ``ExecutionAgent.execute``). No agent module is modified.
- **Fail-safe**: every node is wrapped so an exception never propagates out
  of the graph; the node records ``error`` + ``status="failed"`` and the
  next conditional edge diverts the run to human review. The executor can
  therefore never run after a failed upstream node.
- **Nodes return partial state updates**; they never mutate the state dict
  or shared Pydantic models in place.
- ``build_dispute_graph(...)`` accepts optional agent instances purely for
  testing; production callers use the defaults.
"""
from __future__ import annotations

import logging
from functools import wraps

from langgraph.graph import END, START, StateGraph

from src.agents.arbitrator import ArbitrationAgent
from src.agents.classifier import ClassifierAgent
from src.agents.collector import CollectorAgent
from src.agents.executor import (
    ExecutionAgent,
    STATUS_ESCALATED as EXECUTION_STATUS_ESCALATED,
    STATUS_EXECUTED as EXECUTION_STATUS_EXECUTED,
)
from src.agents.fairness import FairnessAgent, FairnessRecommendation
from src.core.debate import DebateEngine
from src.core.workflow_state import (
    STATUS_ESCALATED,
    STATUS_FAILED,
    STATUS_IN_PROGRESS,
    STATUS_RESOLVED,
    DisputeWorkflowState,
)
from src.models.dispute_state import FairnessAssessmentInput

logger = logging.getLogger(__name__)

# Node names (also used as LangGraph node ids).
NODE_COLLECTOR = "collector"
NODE_CLASSIFIER = "classifier"
NODE_DEBATE = "debate"
NODE_ARBITRATOR = "arbitrator"
# Note: LangGraph forbids node ids that collide with state keys, so this
# node is "fairness_agent" while the state artifact stays ``fairness``.
NODE_FAIRNESS = "fairness_agent"
NODE_EXECUTOR = "executor"
NODE_HUMAN_REVIEW = "human_review"


# ----------------------------------------------------------------------
# Node error wrapper
# ----------------------------------------------------------------------


def _safe_node(node_name: str):
    """Decorator: catch any exception, record a structured error, and mark
    the run as failed so the next conditional edge routes to human review."""

    def decorator(fn):
        @wraps(fn)
        async def wrapper(state: DisputeWorkflowState) -> dict:
            try:
                return await fn(state)
            except Exception as exc:  # noqa: BLE001 - deliberate fail-safe
                logger.exception("Workflow node '%s' failed", node_name)
                return {
                    "status": STATUS_FAILED,
                    "error": {
                        "node": node_name,
                        "type": type(exc).__name__,
                        "message": str(exc),
                    },
                    "human_review_reason": (
                        f"Workflow node '{node_name}' failed: "
                        f"{type(exc).__name__}: {exc}"
                    ),
                }

        return wrapper

    return decorator


def _as_analysis(content) -> dict:
    """Debate round-0 contents are dicts; later rebuttals are strings.
    The Fairness Agent requires dict analyses, so wrap strings."""
    return content if isinstance(content, dict) else {"summary": str(content)}


# ----------------------------------------------------------------------
# Graph factory
# ----------------------------------------------------------------------


def build_dispute_graph(
    collector: CollectorAgent | None = None,
    classifier: ClassifierAgent | None = None,
    debate_engine: DebateEngine | None = None,
    arbitrator: ArbitrationAgent | None = None,
    fairness_agent: FairnessAgent | None = None,
    executor: ExecutionAgent | None = None,
):
    """Compile and return the dispute-resolution LangGraph.

    All arguments are optional injectable agent instances (used by tests);
    production callers omit them to get the real agents.
    """
    collector = collector or CollectorAgent()
    classifier = classifier or ClassifierAgent()
    debate_engine = debate_engine or DebateEngine()
    arbitrator = arbitrator or ArbitrationAgent()
    fairness_agent = fairness_agent or FairnessAgent()
    executor = executor or ExecutionAgent()

    # -- Nodes ----------------------------------------------------------

    @_safe_node(NODE_COLLECTOR)
    async def collector_node(state: DisputeWorkflowState) -> dict:
        context = await collector.collect(
            report_text=state["report_text"],
            order_id=state["order_id"],
            reporter=state.get("reporter", "passenger"),
            evidence=state.get("evidence") or [],
            language=state.get("language", "en"),
        )
        return {"context": context, "status": STATUS_IN_PROGRESS}

    @_safe_node(NODE_CLASSIFIER)
    async def classifier_node(state: DisputeWorkflowState) -> dict:
        result = await classifier.classify(state["context"])
        # Preserve the legacy orchestrator side-effect: propagate the
        # classified dispute type onto the context (immutably).
        context = state["context"].model_copy(
            update={"type": result.dispute_type}
        )
        return {"classification": result, "context": context}

    @_safe_node(NODE_DEBATE)
    async def debate_node(state: DisputeWorkflowState) -> dict:
        history = await debate_engine.debate(state["context"])
        return {"debate_history": history}

    @_safe_node(NODE_ARBITRATOR)
    async def arbitrator_node(state: DisputeWorkflowState) -> dict:
        # Preserve the legacy orchestrator convention: the round-0 debate
        # entries carry the passenger / driver / policy analyses.
        history = state.get("debate_history") or []
        decision = await arbitrator.arbitrate(
            context=state["context"].model_dump(),
            passenger_analysis=_as_analysis(history[0]["content"]) if len(history) > 0 else {},
            driver_analysis=_as_analysis(history[1]["content"]) if len(history) > 1 else {},
            policy_evaluation=_as_analysis(history[2]["content"]) if len(history) > 2 else {},
            debate_history=history,
        )
        return {"decision": decision}

    @_safe_node(NODE_FAIRNESS)
    async def fairness_node(state: DisputeWorkflowState) -> dict:
        history = state.get("debate_history") or []
        payload = FairnessAssessmentInput(
            dispute_id=state["context"].dispute_id,
            decision=state["decision"],
            passenger_analysis=_as_analysis(history[0]["content"]) if len(history) > 0 else {},
            driver_analysis=_as_analysis(history[1]["content"]) if len(history) > 1 else {},
            policy_evaluation=_as_analysis(history[2]["content"]) if len(history) > 2 else {},
            debate_history=history,
            context=state["context"].model_dump(),
        )
        assessment = await fairness_agent.assess(payload)
        return {"fairness": assessment}

    @_safe_node(NODE_EXECUTOR)
    async def executor_node(state: DisputeWorkflowState) -> dict:
        execution = await executor.execute(
            state["decision"], state["context"].dispute_id
        )
        if not isinstance(execution, dict):
            raise ValueError("Executor returned no structured result")
        if execution.get("status") == EXECUTION_STATUS_EXECUTED and execution.get("executed") is True:
            return {"execution": execution, "status": STATUS_RESOLVED}
        if execution.get("status") == EXECUTION_STATUS_ESCALATED and execution.get("executed") is False:
            return {
                "execution": execution,
                "status": STATUS_ESCALATED,
                "human_review_reason": "Executor requested human review.",
            }
        message = execution.get("error") or "Executor did not complete the decision."
        return {
            "execution": execution,
            "status": STATUS_FAILED,
            "error": {"node": NODE_EXECUTOR, "type": "ExecutionFailed", "message": str(message)},
            "human_review_reason": f"Execution failed; human review required: {message}",
        }

    async def human_review_node(state: DisputeWorkflowState) -> dict:
        """Terminal bookkeeping node for every non-execution exit path."""
        # A failed node already recorded status/error/reason — keep them.
        if state.get("status") == STATUS_FAILED:
            return {"execution": None}
        decision = state.get("decision")
        if decision is not None and decision.human_review_needed:
            return {
                "status": STATUS_ESCALATED,
                "human_review_reason": "Arbitrator requested human review.",
                "execution": None,
            }
        # Fairness-driven escalation (arbitrator already ran).
        fairness = state.get("fairness")
        if fairness is not None:
            reason = fairness.reason or "Fairness assessment requires human review."
            return {
                "status": STATUS_ESCALATED,
                "human_review_reason": reason,
                "execution": None,
            }
        # Classifier-driven escalation — preserve the legacy reason string.
        return {
            "status": STATUS_ESCALATED,
            "human_review_reason": "Safety/legal issue requires human review",
            "execution": None,
        }

    # -- Conditional edges ----------------------------------------------

    def _route_or_human_review(next_node: str):
        """Router used after nodes with a single legitimate successor:
        divert to human review only when the node failed."""
        def router(state: DisputeWorkflowState) -> str:
            if state.get("error"):
                return NODE_HUMAN_REVIEW
            return next_node

        return router

    def route_after_classifier(state: DisputeWorkflowState) -> str:
        """Classifier gate: safety/legal issues bypass debate entirely."""
        if state.get("error"):
            return NODE_HUMAN_REVIEW
        classification = state.get("classification")
        if classification is not None and classification.requires_human:
            return NODE_HUMAN_REVIEW
        return NODE_DEBATE

    def route_after_fairness(state: DisputeWorkflowState) -> str:
        """Only decisions cleared by both the arbitrator and fairness may execute."""
        if state.get("error"):
            return NODE_HUMAN_REVIEW
        decision = state.get("decision")
        if decision is None or decision.human_review_needed:
            return NODE_HUMAN_REVIEW
        fairness = state.get("fairness")
        if fairness is None:
            # No assessment available — cannot attest fairness; do not execute.
            return NODE_HUMAN_REVIEW
        if fairness.requires_human_review:
            return NODE_HUMAN_REVIEW
        if fairness.recommendation != FairnessRecommendation.PROCEED:
            return NODE_HUMAN_REVIEW
        return NODE_EXECUTOR

    # -- Wiring ----------------------------------------------------------

    builder = StateGraph(DisputeWorkflowState)
    builder.add_node(NODE_COLLECTOR, collector_node)
    builder.add_node(NODE_CLASSIFIER, classifier_node)
    builder.add_node(NODE_DEBATE, debate_node)
    builder.add_node(NODE_ARBITRATOR, arbitrator_node)
    builder.add_node(NODE_FAIRNESS, fairness_node)
    builder.add_node(NODE_EXECUTOR, executor_node)
    builder.add_node(NODE_HUMAN_REVIEW, human_review_node)

    builder.add_edge(START, NODE_COLLECTOR)

    builder.add_conditional_edges(
        NODE_COLLECTOR,
        _route_or_human_review(NODE_CLASSIFIER),
        {NODE_CLASSIFIER: NODE_CLASSIFIER, NODE_HUMAN_REVIEW: NODE_HUMAN_REVIEW},
    )
    builder.add_conditional_edges(
        NODE_CLASSIFIER,
        route_after_classifier,
        {NODE_DEBATE: NODE_DEBATE, NODE_HUMAN_REVIEW: NODE_HUMAN_REVIEW},
    )
    builder.add_conditional_edges(
        NODE_DEBATE,
        _route_or_human_review(NODE_ARBITRATOR),
        {NODE_ARBITRATOR: NODE_ARBITRATOR, NODE_HUMAN_REVIEW: NODE_HUMAN_REVIEW},
    )
    builder.add_conditional_edges(
        NODE_ARBITRATOR,
        _route_or_human_review(NODE_FAIRNESS),
        {NODE_FAIRNESS: NODE_FAIRNESS, NODE_HUMAN_REVIEW: NODE_HUMAN_REVIEW},
    )
    builder.add_conditional_edges(
        NODE_FAIRNESS,
        route_after_fairness,
        {NODE_EXECUTOR: NODE_EXECUTOR, NODE_HUMAN_REVIEW: NODE_HUMAN_REVIEW},
    )

    builder.add_edge(NODE_EXECUTOR, END)
    builder.add_edge(NODE_HUMAN_REVIEW, END)

    return builder.compile()
