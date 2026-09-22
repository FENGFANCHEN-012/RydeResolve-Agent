"""
Agent 6: Arbitration Agent
Synthesizes all perspectives and generates final verdict.
"""
from pydantic import BaseModel, Field
from enum import Enum

from src.config import CONFIDENCE_THRESHOLD_HIGH, CONFIDENCE_THRESHOLD_LOW


class Verdict(str, Enum):
    UPHELD = "upheld"
    PARTIALLY_UPHELD = "partially_upheld"
    DISMISSED = "dismissed"


class Decision(BaseModel):
    verdict: Verdict
    confidence: float = Field(ge=0.0, le=1.0)
    refund_amount: float | None = None
    compensation: str | None = None
    driver_penalty: str | None = None
    rationale: str
    policy_references: list[str] = []
    escalation_recommended: bool = False
    human_review_needed: bool = False


class ArbitrationAgent:
    """Generates final arbitration decision based on all agent inputs."""

    def __init__(self):
        self.name = "Arbitrator"

    async def arbitrate(
        self,
        context: dict,
        passenger_analysis: dict,
        driver_analysis: dict,
        policy_evaluation: dict,
        debate_history: list[dict],
    ) -> Decision:
        """
        Synthesize all agent outputs into a final decision.

        Confidence = w1 * evidence_strength + w2 * policy_alignment + w3 * agent_agreement
        """
        # TODO: Integrate Hunyuan LLM with arbitration prompt
        decision = Decision(
            verdict=Verdict.PARTIALLY_UPHELD,
            confidence=0.0,
            rationale="",
        )

        # Determine if human review is needed based on confidence
        if decision.confidence <= CONFIDENCE_THRESHOLD_LOW:
            decision.human_review_needed = True
        elif decision.confidence <= CONFIDENCE_THRESHOLD_HIGH:
            decision.escalation_recommended = True

        return decision
