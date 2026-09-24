"""
Agent Orchestrator

Thin wrapper around the LangGraph dispute-resolution workflow defined in
``src/core/workflow.py``. It owns no pipeline logic: it translates the
public ``resolve(...)`` API into an initial graph state, runs the graph,
and translates the final state back into the legacy response shape so the
FastAPI layer and frontend remain unchanged.

Legacy behaviour preserved:
- ``resolve(report_text, order_id, reporter, evidence, language) -> dict``
- classifier escalations return ``status="escalated_to_human"`` with the
  ``platform_data`` payload and the legacy reason string
- the resolved path returns the same top-level keys as before, plus a new
  additive ``"fairness"`` key for the audit trail
"""
from src.agents.collector import DisputeContext, EvidenceItem
from src.core.workflow import build_dispute_graph
from src.core.workflow_state import (
    STATUS_ESCALATED,
    STATUS_FAILED,
    STATUS_RESOLVED,
    DisputeWorkflowState,
)


class Orchestrator:
    """
    Public entry point for the dispute-resolution pipeline:

    1. Collect -> 2. Classify -> 3. Debate -> 4. Arbitrate
    -> 5. Fairness check -> 6. Execute / Escalate to human review
    """

    def __init__(self, workflow=None):
        # The compiled LangGraph; injectable for tests.
        self.workflow = workflow or build_dispute_graph()

    async def resolve(
        self,
        report_text: str,
        order_id: str,
        reporter: str = "passenger",
        evidence: list[EvidenceItem] | None = None,
        language: str = "en",
    ) -> dict:
        """
        Run the full dispute resolution pipeline with rich platform context.

        Args:
            report_text: User's dispute description
            order_id: Ryde order ID
            reporter: Who filed the dispute ("passenger" or "driver")
            evidence: List of uploaded evidence items
            language: Language code (en, zh, ms, ta)

        Returns:
            Full resolution result with classification, verdict, fairness
            assessment, and execution status
        """
        final_state: DisputeWorkflowState = await self.workflow.ainvoke(
            {
                "report_text": report_text,
                "order_id": order_id,
                "reporter": reporter,
                "evidence": evidence or [],
                "language": language,
            }
        )
        return self._to_response(final_state)

    # ------------------------------------------------------------------
    # Response translation
    # ------------------------------------------------------------------

    def _to_response(self, state: DisputeWorkflowState) -> dict:
        status = state.get("status")
        context: DisputeContext | None = state.get("context")
        classification = state.get("classification")
        decision = state.get("decision")
        fairness = state.get("fairness")
        execution = state.get("execution")
        debate_history = state.get("debate_history") or []

        # -- Node failure: fail loudly but safely ----------------------
        if status == STATUS_FAILED:
            response: dict = {
                "status": STATUS_FAILED,
                "reason": state.get("human_review_reason")
                or "Workflow failed; dispute routed to human review.",
                "error": state.get("error"),
            }
            if context is not None:
                response["dispute_id"] = context.dispute_id
                response["order_id"] = context.order_id
            if classification is not None:
                response["classification"] = classification.model_dump()
            if decision is not None:
                response["verdict"] = decision.model_dump()
            if fairness is not None:
                response["fairness"] = fairness.model_dump()
            if execution is not None:
                response["execution"] = execution
            return response

        # -- Escalation to human review --------------------------------
        if status == STATUS_ESCALATED:
            if context is not None:
                response = {
                    "dispute_id": context.dispute_id,
                    "order_id": context.order_id,
                    "status": STATUS_ESCALATED,
                    "reason": state.get("human_review_reason")
                    or "Requires human review",
                    "platform_data": self._platform_data(context),
                }
            else:
                response = {
                    "dispute_id": None,
                    "status": STATUS_ESCALATED,
                    "reason": state.get("human_review_reason")
                    or "Requires human review",
                }
            if classification is not None:
                response["classification"] = classification.model_dump()
            # Fairness-driven escalation: expose the full audit trail
            # (decision + fairness assessment) for the human reviewer.
            if decision is not None:
                response["verdict"] = decision.model_dump()
            if fairness is not None:
                response["fairness"] = fairness.model_dump()
            response["execution"] = execution  # Present if the executor requested review
            response["debate_rounds"] = len(debate_history)
            return response

        # -- Resolved (executor ran) ------------------------------------
        if context is None or decision is None:
            # Defensive: should not happen on the resolved path.
            return {
                "status": STATUS_FAILED,
                "reason": "Workflow finished without a decision.",
                "error": {"node": "orchestrator", "type": "InvariantError",
                          "message": "resolved state missing context/decision"},
            }

        response = {
            "dispute_id": context.dispute_id,
            "order_id": context.order_id,
            "status": STATUS_RESOLVED,
            "classification": classification.model_dump() if classification else None,
            "verdict": decision.model_dump(),
            "fairness": fairness.model_dump() if fairness else None,
            "execution": execution,
            "debate_rounds": len(debate_history),
            "platform_data_summary": {
                "trip_distance_km": context.trip.get("actual_distance_km") if context.trip else None,
                "fare_discrepancy": self._calc_fare_discrepancy(context),
                "chat_messages_count": len(context.chat_log) if context.chat_log else 0,
                "gps_points_count": len(context.gps_trace) if context.gps_trace else 0,
                "evidence_count": len(context.evidence),
                "rider_rating": context.rider_profile.get("rating") if context.rider_profile else None,
                "driver_rating": context.driver_profile.get("rating") if context.driver_profile else None,
            },
        }
        return response

    # ------------------------------------------------------------------
    # Legacy helpers (unchanged)
    # ------------------------------------------------------------------

    @staticmethod
    def _platform_data(context: DisputeContext) -> dict:
        """Legacy ``platform_data`` payload for escalated disputes."""
        return {
            "trip": context.trip,
            "payment": context.payment,
            "chat_log": context.chat_log,
            "gps_trace": context.gps_trace,
            "rider_profile": context.rider_profile,
            "driver_profile": context.driver_profile,
            "evidence": [ev.model_dump() for ev in context.evidence],
        }

    @staticmethod
    def _calc_fare_discrepancy(context: DisputeContext) -> float | None:
        """Calculate fare discrepancy from platform data."""
        if not context.payment:
            return None
        estimated = context.payment.get("estimated_fare", 0)
        actual = context.payment.get("total_fare", 0)
        if estimated and actual:
            return round(actual - estimated, 2)
        return None
