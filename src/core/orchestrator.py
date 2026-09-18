"""
Agent Orchestrator
Coordinates the full dispute resolution pipeline.
"""
from src.agents.collector import CollectorAgent, DisputeContext
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
    1. Collect -> 2. Classify -> 3. Debate (parallel) -> 4. Arbitrate -> 5. Execute
    """

    def __init__(self):
        self.collector = CollectorAgent()
        self.classifier = ClassifierAgent()
        self.debate_engine = DebateEngine()
        self.arbitrator = ArbitrationAgent()
        self.executor = ExecutionAgent()

    async def resolve(self, report_text: str, order_id: str) -> dict:
        """Run the full dispute resolution pipeline."""
        # Step 1: Collect information
        context = await self.collector.collect(report_text, order_id)

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
            "classification": classification.model_dump(),
            "verdict": decision.model_dump(),
            "execution": execution_result,
            "debate_rounds": len(debate_history),
        }
