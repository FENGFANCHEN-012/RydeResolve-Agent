"""
Agent 2: Dispute Classification Agent
Auto-classifies dispute type and urgency level using LLM.
"""
from enum import Enum
from typing import Optional
from pydantic import BaseModel

from src.agents.collector import DisputeContext, DisputeType


class UrgencyLevel(str, Enum):
    P0 = "P0"  # Critical: safety, legal
    P1 = "P1"  # High: financial loss
    P2 = "P2"  # Medium: service complaint
    P3 = "P3"  # Low: minor dispute


class ClassificationResult(BaseModel):
    dispute_type: DisputeType
    urgency: UrgencyLevel
    requires_human: bool  # safety/legal issues
    confidence: float
    reasoning: str


class ClassifierAgent:
    """Classifies disputes into categories and urgency levels."""

    def __init__(self):
        self.name = "Classifier"

    async def classify(self, context: DisputeContext) -> ClassificationResult:
        """
        Use Tencent Hunyuan LLM to:
        1. Identify dispute type from 6 categories
        2. Assess urgency (P0-P3)
        3. Flag if human intervention is required (safety/legal)
        """
        # TODO: Integrate Hunyuan LLM call
        # Safety/legal disputes (accidents, injury) -> P0, requires_human=True
        pass
