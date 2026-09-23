"""
Agent 2: Dispute Classification Agent

Hybrid classification: fast keyword-based P0 safety detection + LLM-based
classification for nuanced dispute types. Works offline for safety checks,
uses Gemini LLM for accurate type/urgency classification.
"""
import json
import logging
import re
from enum import Enum
from typing import Optional
from pydantic import BaseModel, field_validator

from src.agents.collector import DisputeContext, DisputeType
from src.core.llm_client import LLMClient

logger = logging.getLogger(__name__)


class UrgencyLevel(str, Enum):
    P0 = "P0"  # Critical: safety, legal
    P1 = "P1"  # High: financial loss
    P2 = "P2"  # Medium: service complaint
    P3 = "P3"  # Low: minor dispute


class ClassificationResult(BaseModel):
    dispute_type: Optional[DisputeType] = None
    urgency: UrgencyLevel
    requires_human: bool  # safety/legal issues
    confidence: float
    reasoning: str

    @field_validator("confidence")
    @classmethod
    def _confidence_range(cls, v: float) -> float:
        """Ensure confidence is always between 0.0 and 1.0."""
        if v < 0.0:
            return 0.0
        if v > 1.0:
            return 1.0
        return v


# ------------------------------------------------------------------ #
# P0 critical-safety keywords — checked first for immediate escalation
# ------------------------------------------------------------------ #
_P0_KEYWORDS: list[str] = [
    "accident", "injury", "injured", "assault", "assaulted",
    "crash", "collision", "hospital", "ambulance",
    "bleeding", "unconscious", "concussion", "fracture",
    "trauma", "weapon", "knife", "gun", "threatened",
    "harassment", "sexually", "police", "lawsuit", "sue",
    "legal action", "attacked", "physically", "danger",
    "harm", "hurt", "wounded", "stab", "struck",
]


def _has_p0_keywords(text: str) -> tuple[bool, list[str]]:
    """Check if text contains any P0 safety keywords."""
    text_lower = text.lower()
    # Whole-word match only: plain substring matching flagged "issue" (sue),
    # "stable" (stab), "begun" (gun) etc. as safety incidents.
    matched = [kw for kw in _P0_KEYWORDS if re.search(rf"\b{re.escape(kw)}\b", text_lower)]
    return len(matched) > 0, matched


class ClassifierAgent:
    """
    Hybrid dispute classifier.

    1. Fast keyword scan for P0 safety issues (offline, instant).
    2. LLM-based classification for nuanced dispute types and urgency.
    """

    def __init__(self, llm_client: LLMClient | None = None):
        self.name = "Classifier"
        self._llm = llm_client

    def _get_llm(self) -> LLMClient:
        if self._llm is None:
            self._llm = LLMClient()
        return self._llm



    async def classify(self, context: DisputeContext) -> ClassificationResult:
        """
        Classify a dispute using hybrid approach:
        1. P0 keyword scan (instant, offline).
        2. LLM classification for type, urgency, and confidence.
        """
        description = context.description or ""

        # -- Step 1: Fast P0 safety check --------------------------------
        has_p0, p0_matched = _has_p0_keywords(description)
        if has_p0:
            return ClassificationResult(
                dispute_type=DisputeType.ACCIDENT,
                urgency=UrgencyLevel.P0,
                requires_human=True,
                confidence=min(0.5 + 0.1 * len(p0_matched), 0.95),
                reasoning=(
                    f"P0 safety keywords detected ({', '.join(p0_matched[:3])}). "
                    "This dispute involves a critical safety or legal issue and "
                    "requires immediate human review."
                ),
            )

        # -- Step 2: LLM-based classification ----------------------------
        return await self._llm_classify(context)

    async def _llm_classify(self, context: DisputeContext) -> ClassificationResult:
        """Use Gemini LLM to classify the dispute type and urgency."""

        system_prompt = (
            "You are a dispute classification expert for the Ryde ride-hailing "
            "platform in Singapore. Analyze the dispute report and classify it "
            "into one of the following categories:\n\n"
            "1. route_deviation — Driver took a longer/wrong route causing overcharge\n"
            "2. no_show — Driver or rider did not show up at pickup\n"
            "3. fare_dispute — Incorrect fare calculation, surge pricing issue, overcharge\n"
            "4. cancellation_refund — Dispute over cancellation fees or refund eligibility\n"
            "5. service_quality — Rude behavior, unsafe driving, cleanliness, attitude\n"
            "6. delivery_dispute — Issues with RydeSEND delivery (damaged/lost items, wrong address)\n"
            "7. driver_rights — Driver unfairly penalized, wrongfully charged, account issues\n"
            "8. accident_liability — Physical injury, vehicle damage, collision\n\n"
            "Urgency levels:\n"
            "- P0: Critical safety/legal (assault, injury, harassment, police involved)\n"
            "- P1: High financial impact (fare disputes, cancellation fees, route overcharge)\n"
            "- P2: Medium service complaint (rudeness, cleanliness, minor delays)\n"
            "- P3: Low minor issue (questions, feedback, non-urgent requests)\n\n"
            "Respond ONLY with a valid JSON object (no markdown, no extra text) with:\n"
            "  \"dispute_type\": string (one of the 8 types above, or null if unclear),\n"
            "  \"urgency\": string (P0/P1/P2/P3),\n"
            "  \"requires_human\": boolean (true for P0 or ambiguous cases),\n"
            "  \"confidence\": float (0.0-1.0),\n"
            "  \"reasoning\": string (concise explanation of classification)\n\n"
            "Guidelines:\n"
            "- If the description is ambiguous or doesn't fit any category, set dispute_type to null.\n"
            "- requires_human=true for P0 urgency or when confidence < 0.6.\n"
            "- Be precise: route_deviation is about wrong/longer route, not general fare issues.\n"
            "- cancellation_refund is about cancellation fees, not general refunds.\n"
            "- service_quality covers attitude, driving behavior, cleanliness.\n"
        )

        # Build context-rich user prompt
        user_prompt_parts = [
            f"Dispute Description: {context.description}",
            f"Reporter: {context.reporter}",
            f"Order ID: {context.order_id}",
        ]

        if context.trip:
            user_prompt_parts.append(f"Trip Details: {json.dumps(context.trip)}")
        if context.payment:
            user_prompt_parts.append(f"Payment Details: {json.dumps(context.payment)}")
        if context.chat_log:
            user_prompt_parts.append(f"Chat Log: {json.dumps(context.chat_log)}")
        if context.gps_trace:
            user_prompt_parts.append(f"GPS Trace Available: Yes")
        if context.ratings:
            user_prompt_parts.append(f"Ratings: {json.dumps(context.ratings)}")

        user_prompt = "\n".join(user_prompt_parts)

        try:
            llm = self._get_llm()
            raw_response = await llm.chat_json(
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                temperature=0.2,
            )

            parsed = json.loads(raw_response)

            # Validate and map dispute_type
            type_str = parsed.get("dispute_type")
            dispute_type = None
            if type_str:
                try:
                    dispute_type = DisputeType(type_str)
                except ValueError:
                    # Try to fuzzy match
                    type_lower = type_str.lower().replace(" ", "_").replace("-", "_")
                    for dt in DisputeType:
                        if type_lower in dt.value.lower() or dt.value.lower() in type_lower:
                            dispute_type = dt
                            break

            # Validate urgency
            urgency_str = parsed.get("urgency", "P2")
            try:
                urgency = UrgencyLevel(urgency_str.upper())
            except ValueError:
                urgency = UrgencyLevel.P2

            # Override: if P0 keywords somehow missed, force P0
            if urgency == UrgencyLevel.P0 and dispute_type != DisputeType.ACCIDENT:
                dispute_type = DisputeType.ACCIDENT

            confidence = float(parsed.get("confidence", 0.5))
            requires_human = parsed.get("requires_human", confidence < 0.6)

            # Force human review for P0 regardless of LLM output
            if urgency == UrgencyLevel.P0:
                requires_human = True

            return ClassificationResult(
                dispute_type=dispute_type,
                urgency=urgency,
                requires_human=requires_human,
                confidence=confidence,
                reasoning=parsed.get("reasoning", "LLM classification completed."),
            )

        except json.JSONDecodeError as exc:
            logger.warning("LLM returned invalid JSON: %s", exc)
            return self._fallback_classification(
                context, f"LLM returned invalid JSON: {exc}"
            )
        except Exception as exc:
            logger.warning("LLM classification failed: %s", exc)
            return self._fallback_classification(
                context, f"LLM classification failed: {exc}"
            )

    def _fallback_classification(
        self, context: DisputeContext, reason: str
    ) -> ClassificationResult:
        """
        Safe fallback when LLM fails.
        Returns ambiguous result requiring human review.
        """
        return ClassificationResult(
            dispute_type=None,
            urgency=UrgencyLevel.P3,
            requires_human=True,
            confidence=0.3,
            reasoning=(
                f"Classification failed: {reason}. "
                "The dispute requires human review for manual classification."
            ),
        )
