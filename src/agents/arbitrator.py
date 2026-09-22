"""
Agent 6: Arbitration Agent

Synthesizes all perspectives and generates final verdict.
Uses LLM to produce evidence-grounded decisions with real Ryde policies.
"""
import json
import logging

from pydantic import BaseModel, Field
from enum import Enum

from src.config import CONFIDENCE_THRESHOLD_HIGH, CONFIDENCE_THRESHOLD_LOW
from src.core.llm_client import LLMClient

logger = logging.getLogger(__name__)


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

    def __init__(self, llm_client: LLMClient | None = None):
        self.name = "Arbitrator"
        self._llm_client = llm_client

    def _get_llm_client(self) -> LLMClient | None:
        if self._llm_client is None:
            try:
                self._llm_client = LLMClient()
            except Exception as exc:
                logger.warning("Could not initialise LLMClient: %s", exc)
                self._llm_client = None  # type: ignore[assignment]
        return self._llm_client  # type: ignore[return-value]

    @staticmethod
    def _parse_llm_json(raw: str) -> dict | None:
        """Parse an LLM JSON response, stripping markdown fences if needed."""
        if not raw or not isinstance(raw, str):
            return None

        text = raw.strip()

        # Strip markdown code fences
        if text.startswith("```"):
            lines = text.split("\n")
            lines = [l for l in lines if not l.strip().startswith("```")]
            text = "\n".join(lines).strip()

        # Try direct parse
        try:
            result = json.loads(text)
        except json.JSONDecodeError:
            start = text.find("{")
            end = text.rfind("}")
            if start == -1 or end == -1 or end <= start:
                return None
            try:
                result = json.loads(text[start : end + 1])
            except json.JSONDecodeError:
                return None

        if not isinstance(result, dict):
            return None
        return result

    @staticmethod
    def _safe_decision(reason: str) -> Decision:
        """Return a safe decision requiring human review."""
        return Decision(
            verdict=Verdict.PARTIALLY_UPHELD,
            confidence=0.0,
            rationale=reason,
            human_review_needed=True,
        )

    async def arbitrate(
        self,
        context: dict,
        passenger_analysis: dict,
        driver_analysis: dict,
        policy_evaluation: dict,
        debate_history: list[dict],
    ) -> Decision:
        """
        Synthesize all agent outputs into a final decision using LLM.

        The arbitrator considers:
        - Passenger's evidence-grounded analysis
        - Driver's evidence-grounded analysis
        - Policy compliance evaluation
        - Debate history (rebuttals)
        - Platform data (trip, payment, GPS, chat)
        """
        llm = self._get_llm_client()
        if llm is None:
            return self._safe_decision("LLM client is not available. Human review required.")

        # Build the arbitration prompt
        system_prompt = (
            "You are a neutral arbitrator resolving a ride-hailing dispute "
            "on the Ryde platform. Your job is to synthesize all evidence "
            "and arguments from both sides and produce a fair, evidence-based decision.\n\n"
            "Rules:\n"
            "- Base your decision ONLY on the evidence and arguments provided.\n"
            "- Do not invent facts, GPS records, chat messages, or policies.\n"
            "- Consider both passenger and driver perspectives equally.\n"
            "- Apply Ryde platform policies fairly.\n"
            "- Be transparent about your reasoning.\n"
            "- If evidence is insufficient, recommend human review.\n\n"
            "Respond ONLY with a valid JSON object (no markdown, no extra text) "
            "with exactly these keys:\n"
            '  "verdict": string (one of: "upheld", "partially_upheld", "dismissed"),\n'
            '  "confidence": float (0.0-1.0),\n'
            '  "refund_amount": number or null (refund in SGD if applicable),\n'
            '  "compensation": string or null (description of compensation),\n'
            '  "driver_penalty": string or null (description of driver action),\n'
            '  "rationale": string (concise evidence-based reasoning),\n'
            '  "policy_references": list of strings,\n'
            '  "escalation_recommended": boolean,\n'
            '  "human_review_needed": boolean\n'
        )

        # Build user prompt with all context
        user_prompt_parts = [
            "=== DISPUTE CONTEXT ===",
            json.dumps(context, indent=2, default=str),
            "\n=== PASSENGER ANALYSIS ===",
            json.dumps(passenger_analysis, indent=2, default=str),
            "\n=== DRIVER ANALYSIS ===",
            json.dumps(driver_analysis, indent=2, default=str),
            "\n=== POLICY EVALUATION ===",
            json.dumps(policy_evaluation, indent=2, default=str),
            "\n=== DEBATE HISTORY ===",
        ]

        # Add debate history (limit to avoid token overflow)
        for entry in debate_history[-6:]:
            user_prompt_parts.append(
                f"Round {entry['round']} - {entry['speaker']} ({entry.get('type', 'unknown')}):\n"
                f"{json.dumps(entry['content'], indent=2, default=str)[:500]}"
            )

        user_prompt_parts.append(
            "\nBased on all the above evidence and arguments, render your final decision. "
            "Respond ONLY with valid JSON."
        )

        user_prompt = "\n".join(user_prompt_parts)

        try:
            raw = await llm.chat_json(
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                temperature=0.1,
            )
        except Exception as exc:
            logger.warning("ArbitrationAgent LLM call failed: %s", exc)
            return self._safe_decision(f"LLM call failed: {exc}")

        # Parse JSON response
        parsed = self._parse_llm_json(raw)
        if parsed is None:
            return self._safe_decision("LLM returned invalid JSON. Human review required.")

        # Extract verdict
        verdict_str = parsed.get("verdict", "partially_upheld").lower()
        try:
            verdict = Verdict(verdict_str)
        except ValueError:
            verdict = Verdict.PARTIALLY_UPHELD

        # Build decision
        confidence = float(parsed.get("confidence", 0.0))
        confidence = max(0.0, min(1.0, confidence))

        decision = Decision(
            verdict=verdict,
            confidence=confidence,
            refund_amount=parsed.get("refund_amount"),
            compensation=parsed.get("compensation"),
            driver_penalty=parsed.get("driver_penalty"),
            rationale=parsed.get("rationale", "No rationale provided."),
            policy_references=parsed.get("policy_references", []),
            escalation_recommended=parsed.get("escalation_recommended", False),
            human_review_needed=parsed.get("human_review_needed", False),
        )

        # Override human_review_needed based on confidence thresholds
        if decision.confidence <= CONFIDENCE_THRESHOLD_LOW:
            decision.human_review_needed = True
        elif decision.confidence <= CONFIDENCE_THRESHOLD_HIGH:
            decision.escalation_recommended = True

        return decision
