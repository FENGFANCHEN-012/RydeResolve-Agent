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
from src.config import LLM_API_KEY

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
    """Check if text contains any P0 safety keywords (word-boundary match)."""
    text_lower = text.lower()
    matched = []
    for kw in _P0_KEYWORDS:
        # Use word boundaries to avoid substring false positives
        # (e.g. "sue" inside "issue", "hurt" inside "trip")
        pattern = r"\b" + re.escape(kw) + r"\b"
        if re.search(pattern, text_lower):
            matched.append(kw)
    return len(matched) > 0, matched


# ------------------------------------------------------------------ #
# Deterministic keyword classification — ordered by priority.
# The order matters: higher-priority categories appear first so that
# multi-category disputes resolve to the most serious type.
# ------------------------------------------------------------------ #
_KEYWORD_CATEGORIES: list[tuple[DisputeType, list[str], UrgencyLevel]] = [
    # no_show takes priority over cancellation_refund because
    # "driver never arrived and I want a refund" should classify as no_show
    (DisputeType.NO_SHOW, [
        "no-show", "no show", "never arrived", "didn't arrive",
        "did not arrive", "waited at pickup", "never showed up",
        "didn't show up", "did not show up",
    ], UrgencyLevel.P1),

    (DisputeType.DELIVERY, [
        "rydesend", "delivery", "package", "parcel",
    ], UrgencyLevel.P2),

    (DisputeType.DRIVER_RIGHTS, [
        "driver account", "suspension", "suspended", "reinstated",
        "unfair penalty", "wrongfully suspended", "account reinstated",
    ], UrgencyLevel.P1),

    (DisputeType.ROUTE_DEVIATION, [
        "longer route", "detour", "wrong way", "missed exit",
        "route deviation", "deviated from",
    ], UrgencyLevel.P1),

    # CANCELLATION must come before FARE so that "cancellation fee" is
    # not misclassified as a fare dispute due to "charged" matching FARE.
    (DisputeType.CANCELLATION, [
        "cancel", "cancellation", "cancellation fee", "refund",
    ], UrgencyLevel.P1),

    (DisputeType.FARE, [
        "fare", "overcharge", "overcharged", "surge", "charged",
    ], UrgencyLevel.P1),

    (DisputeType.SERVICE_QUALITY, [
        "rude", "dirty", "attitude", "speeding", "reckless",
        "cleanliness", "unprofessional", "shouted", "smelled",
    ], UrgencyLevel.P2),
]


def _keyword_classify(text: str) -> tuple[Optional[DisputeType], Optional[UrgencyLevel], list[str]]:
    """
    Deterministic keyword classification.

    Categories are checked in priority order so that higher-priority
    types (e.g. no_show) win over lower-priority types (e.g.
    cancellation_refund) when both match.

    Multi-word phrases use substring matching. Single-word keywords
    use word-boundary matching to avoid false positives (e.g. "fare"
    inside "welfare").

    Returns (dispute_type, urgency, matched_keywords) or (None, None, [])
    if no keywords match.
    """
    text_lower = text.lower()
    for dtype, keywords, urgency in _KEYWORD_CATEGORIES:
        matched = []
        for kw in keywords:
            if " " in kw:
                # Multi-word phrase: substring match
                if kw in text_lower:
                    matched.append(kw)
            else:
                # Single word: word-boundary match to avoid false positives
                pattern = r"\b" + re.escape(kw) + r"\b"
                if re.search(pattern, text_lower):
                    matched.append(kw)
        if matched:
            return dtype, urgency, matched
    return None, None, []


class ClassifierAgent:
    """
    Hybrid dispute classifier.

    1. Fast keyword scan for P0 safety issues (offline, instant).
    2. If context.type is already a valid DisputeType, use it as a
       strong deterministic signal.
    3. Deterministic keyword classification for common dispute types.
    4. LLM-based classification for nuanced cases (only when an API
       key is available or a mock client is injected).
    """

    def __init__(self, llm_client: LLMClient | None = None):
        self.name = "Classifier"
        self._llm = llm_client

    def _get_llm(self) -> LLMClient:
        if self._llm is None:
            self._llm = LLMClient()
        return self._llm

    def _has_api_key(self) -> bool:
        """Check whether a configured LLM_API_KEY is available."""
        return bool(LLM_API_KEY)

    async def classify(self, context: DisputeContext) -> ClassificationResult:
        """
        Classify a dispute using hybrid approach:
        1. P0 keyword scan (instant, offline).
        2. If context.type is already a valid DisputeType, use it.
        3. Deterministic keyword classification.
        4. LLM classification (only if API key or mock client available).
        """
        description = context.description or ""

        # -- Step 1: Fast P0 safety check (always runs first) ----------
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

        # -- Step 2: Use pre-existing context.type as a strong signal ---
        if context.type is not None:
            dtype = context.type
            kw_dtype, kw_urgency, kw_matched = _keyword_classify(description)
            # If keywords agree with context.type, boost confidence
            if kw_dtype == dtype:
                return ClassificationResult(
                    dispute_type=dtype,
                    urgency=kw_urgency or UrgencyLevel.P2,
                    requires_human=False,
                    confidence=0.78,
                    reasoning=(
                        f"Dispute type '{dtype.value}' confirmed by both "
                        f"context.type and keyword match ({', '.join(kw_matched[:3])})."
                    ),
                )
            # context.type is set but keywords don't match — still trust it
            # but with slightly lower confidence
            return ClassificationResult(
                dispute_type=dtype,
                urgency=UrgencyLevel.P2,
                requires_human=False,
                confidence=0.70,
                reasoning=(
                    f"Dispute type '{dtype.value}' provided from context. "
                    "Keyword scan did not corroborate but pre-existing type is trusted."
                ),
            )

        # -- Step 3: Deterministic keyword classification ---------------
        kw_dtype, kw_urgency, kw_matched = _keyword_classify(description)
        if kw_dtype is not None:
            return ClassificationResult(
                dispute_type=kw_dtype,
                urgency=kw_urgency or UrgencyLevel.P2,
                requires_human=False,
                confidence=0.75,
                reasoning=(
                    f"Classified as '{kw_dtype.value}' based on keyword "
                    f"match ({', '.join(kw_matched[:3])})."
                ),
            )

        # -- Step 4: LLM-based classification (if available) ------------
        # Only attempt LLM if there's a real API key or an injected mock client
        if self._llm is not None or self._has_api_key():
            try:
                return await self._llm_classify(context)
            except Exception as exc:
                logger.warning("LLM classification failed: %s", exc)
                return self._fallback_classification(
                    context, f"LLM classification failed: {exc}"
                )

        # -- Step 5: Unknown — safe fallback ----------------------------
        return self._fallback_classification(
            context,
            "No API key available and no keywords matched. "
            "Unable to determine dispute type deterministically."
        )

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
        except Exception as exc:
            logger.warning("LLM call failed: %s", exc)
            return self._fallback_classification(
                context, f"LLM classification failed: {exc}"
            )

        # Try to parse JSON
        parsed = self._parse_llm_json(raw_response)
        if parsed is None:
            return self._fallback_classification(
                context, "LLM returned invalid JSON."
            )

        # Validate and map dispute_type
        type_str = parsed.get("dispute_type")
        dispute_type = None
        if type_str:
            try:
                dispute_type = DisputeType(type_str)
            except ValueError:
                # Try to fuzzy match
                type_lower = str(type_str).lower().replace(" ", "_").replace("-", "_")
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

    def _fallback_classification(
        self, context: DisputeContext, reason: str
    ) -> ClassificationResult:
        """
        Safe fallback when LLM fails or no keywords match.
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

    @staticmethod
    def _parse_llm_json(raw: str) -> dict | None:
        """
        Attempt to parse the LLM response as JSON.
        Strips markdown code fences and extracts embedded JSON.
        Returns None if parsing fails.
        """
        if not raw or not isinstance(raw, str):
            return None

        text = raw.strip()

        # Remove markdown code fences if present
        if text.startswith("```"):
            lines = text.split("\n")
            lines = [l for l in lines if not l.strip().startswith("```")]
            text = "\n".join(lines).strip()

        # Try direct parse first
        try:
            result = json.loads(text)
        except json.JSONDecodeError:
            # Try to extract the first JSON object from the text
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
