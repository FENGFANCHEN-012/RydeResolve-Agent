"""
Agent Orchestrator
Coordinates the full dispute resolution pipeline.
"""
from src.agents.collector import CollectorAgent, DisputeContext, EvidenceItem
from src.agents.classifier import ClassifierAgent, ClassificationResult
from src.agents.passenger import PassengerAgent
from src.agents.driver import DriverAgent
from src.agents.policy import PolicyAgent
from src.agents.arbitrator import ArbitrationAgent, Decision
from src.agents.executor import ExecutionAgent
from src.core.debate import DebateEngine


class Orchestrator:
    """
    Main pipeline:
    1. Collect (with Ryde API + evidence) -> 2. Classify -> 3. Debate -> 4. Arbitrate -> 5. Execute
    """

    def __init__(self):
        self.collector = CollectorAgent()
        self.classifier = ClassifierAgent()
        self.debate_engine = DebateEngine()
        self.arbitrator = ArbitrationAgent()
        self.executor = ExecutionAgent()

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
            Full resolution result with classification, verdict, and execution status
        """
        # Step 1: Collect information (from Ryde API + user report + evidence)
        context = await self.collector.collect(
            report_text=report_text,
            order_id=order_id,
            reporter=reporter,
            evidence=evidence or [],
            language=language,
        )

        # Step 2: Classify dispute
        classification = await self.classifier.classify(context)
        context.type = classification.dispute_type

        # Check if human intervention required (safety/legal)
        if classification.requires_human:
            return {
                "dispute_id": context.dispute_id,
                "status": "escalated_to_human",
                "reason": "Safety/legal issue requires human review",
                "classification": classification.model_dump(),
                "platform_data": {
                    "trip": context.trip,
                    "payment": context.payment,
                    "chat_log": context.chat_log,
                    "gps_trace": context.gps_trace,
                    "rider_profile": context.rider_profile,
                    "driver_profile": context.driver_profile,
                    "evidence": [ev.model_dump() for ev in context.evidence],
                },
            }

        # Step 3: Multi-agent debate
        debate_history = await self.debate_engine.debate(context)

        # Step 4: Arbitrate
        decision = await self.arbitrator.arbitrate(
            context=context.model_dump(),
            passenger_analysis=debate_history[0]["content"],
            driver_analysis=debate_history[1]["content"],
            policy_evaluation=debate_history[2]["content"],
            debate_history=debate_history,
        )

        # Step 5: Execute decision
        execution_result = await self.executor.execute(decision, context.dispute_id)

        return {
            "dispute_id": context.dispute_id,
            "order_id": context.order_id,
            "status": "resolved",
            "classification": classification.model_dump(),
            "verdict": decision.model_dump(),
            "execution": execution_result,
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
