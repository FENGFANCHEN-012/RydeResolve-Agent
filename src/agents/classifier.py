"""
Agent 2: Dispute Classification Agent
Deterministic keyword/rule-based classification of dispute type and urgency.
Works fully offline without any LLM API key.

The policies and dispute categories used here are synthetic hackathon demo
data and do not represent any official company policies.
"""
from enum import Enum
from typing import Optional
from pydantic import BaseModel, field_validator

from src.agents.collector import DisputeContext, DisputeType


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
# Keyword rules                                                       #
# ------------------------------------------------------------------ #

# P0 critical-safety keywords — checked first regardless of context.type
_P0_KEYWORDS: list[str] = [
    "accident", "injury", "injured", "assault", "assaulted",
    "crash", "collision", "hospital", "ambulance",
    "bleeding", "unconscious", "concussion", "fracture",
    "trauma", "weapon", "knife", "gun", "threatened",
    "harassment", "sexually", "police", "lawsuit", "sue",
    "legal action", "attacked", "physically", "danger",
    "harm", "hurt", "wounded", "stab", "struck",
]

_ROUTE_KEYWORDS: list[str] = [
    "route", "detour", "deviation", "deviate", "longer route",
    "wrong way", "opposite direction", "missed exit", "missed turn",
    "scenic route", "out of the way", "unnecessary detour",
]

_NO_SHOW_KEYWORDS: list[str] = [
    "no show", "no-show", "didn't show", "did not show", "never showed",
    "never arrived", "didn't arrive", "did not arrive",
    "didn't come", "did not come", "never came",
    "driver didn't", "driver did not", "rider didn't", "rider did not",
    "absent", "not there", "not at the pickup", "waited and waited",
]

_FARE_KEYWORDS: list[str] = [
    "fare", "overcharge", "overcharged", "overcharging",
    "too expensive", "charged more", "excessive charge",
    "wrong price", "price", "amount", "surge", "promo code",
    "discount", "double charged", "charged twice",
]

_CANCELLATION_KEYWORDS: list[str] = [
    "cancel", "cancellation", "cancelled", "canceled",
    "refund", "reimburse", "reimbursement", "cancellation fee",
    "cancel fee", "cancel charge",
]

_SERVICE_KEYWORDS: list[str] = [
    "rude", "impolite", "unprofessional", "dirty", "messy",
    "smelly", "bad smell", "unsafe driving", "reckless",
    "speeding", "harsh braking", "rating", "rated",
    "retaliation", "retaliated", "discrimination", "discriminatory",
    "attitude", "behavior", "behaviour", "complaint about driver",
    "complaint about rider", "yelled", "shouted", "swore",
    "profanity",
]

_DELIVERY_KEYWORDS: list[str] = [
    "delivery", "parcel", "package", "item", "goods",
    "damaged item", "lost item", "missing item",
    "delivered to wrong", "wrong address", "late delivery",
    "package damaged", "item broken", "lost package",
]

_DRIVER_RIGHTS_KEYWORDS: list[str] = [
    "driver rights", "unfair", "wrongfully", "wrongfully charged",
    "driver charged", "driver blamed", "blamed the driver",
    "false accusation", "false claim", "unjustified",
    "driver penalized", "driver penalised", "suspended",
    "deactivated", "account suspended", "wrongful deactivation",
]

# Ordered list of (DisputeType, keywords, urgency) for keyword matching
_TYPE_RULES: list[tuple[DisputeType, list[str], UrgencyLevel]] = [
    (DisputeType.ACCIDENT, _P0_KEYWORDS, UrgencyLevel.P0),
    (DisputeType.ROUTE_DEVIATION, _ROUTE_KEYWORDS, UrgencyLevel.P1),
    (DisputeType.NO_SHOW, _NO_SHOW_KEYWORDS, UrgencyLevel.P1),
    (DisputeType.FARE, _FARE_KEYWORDS, UrgencyLevel.P1),
    (DisputeType.CANCELLATION, _CANCELLATION_KEYWORDS, UrgencyLevel.P1),
    (DisputeType.SERVICE_QUALITY, _SERVICE_KEYWORDS, UrgencyLevel.P2),
    (DisputeType.DELIVERY, _DELIVERY_KEYWORDS, UrgencyLevel.P2),
    (DisputeType.DRIVER_RIGHTS, _DRIVER_RIGHTS_KEYWORDS, UrgencyLevel.P2),
]

# Urgency mapping by dispute type (used when context.type is supplied)
_URGENCY_BY_TYPE: dict[DisputeType, UrgencyLevel] = {
    DisputeType.ACCIDENT: UrgencyLevel.P0,
    DisputeType.ROUTE_DEVIATION: UrgencyLevel.P1,
    DisputeType.NO_SHOW: UrgencyLevel.P1,
    DisputeType.FARE: UrgencyLevel.P1,
    DisputeType.CANCELLATION: UrgencyLevel.P1,
    DisputeType.SERVICE_QUALITY: UrgencyLevel.P2,
    DisputeType.DELIVERY: UrgencyLevel.P2,
    DisputeType.DRIVER_RIGHTS: UrgencyLevel.P2,
}

# Confidence per number of matched keywords
_CONFIDENCE_STEPS: list[float] = [0.0, 0.55, 0.7, 0.8, 0.9]


def _count_matches(text_lower: str, keywords: list[str]) -> int:
    """Count how many keywords from the list appear in the text."""
    return sum(1 for kw in keywords if kw in text_lower)


def _confidence_for_match_count(count: int) -> float:
    """Map a match count to a confidence value (capped at 0.9)."""
    if count <= 0:
        return 0.0
    idx = min(count, len(_CONFIDENCE_STEPS) - 1)
    return _CONFIDENCE_STEPS[idx]


class ClassifierAgent:
    """Classifies disputes into categories and urgency levels using keyword rules."""

    def __init__(self):
        self.name = "Classifier"

    async def classify(self, context: DisputeContext) -> ClassificationResult:
        """
        Classify a dispute deterministically using keyword/rule-based matching.

        Logic:
        1. Normalise the description to lowercase for keyword matching.
        2. Check for P0 safety keywords first. If found, the result is always
           P0 with requires_human=True regardless of any supplied context.type.
        3. If context.type is already supplied AND no P0 keywords were found,
           trust the supplied type and look up its urgency level.
        4. Otherwise, run keyword matching against all dispute-type rule sets
           and select the type with the highest match count.
        5. If no keywords match at all, return an unknown/ambiguous result
           with confidence <= 0.5 and requires_human=True.
        """
        description = context.description or ""
        text = description.lower()

        # -- Step 1: P0 safety check (always takes priority) -----------
        p0_matches = _count_matches(text, _P0_KEYWORDS)
        if p0_matches > 0:
            conf = _confidence_for_match_count(p0_matches)
            # If context.type was already set to something other than accident,
            # we still override to accident because safety takes priority.
            matched_kw = [kw for kw in _P0_KEYWORDS if kw in text]
            return ClassificationResult(
                dispute_type=DisputeType.ACCIDENT,
                urgency=UrgencyLevel.P0,
                requires_human=True,
                confidence=conf,
                reasoning=(
                    f"P0 safety keywords detected in the description "
                    f"({', '.join(matched_kw[:3])}). This dispute involves a "
                    "critical safety or legal issue and requires immediate "
                    "human review. P0 urgency overrides any other classification."
                ),
            )

        # -- Step 2: Use supplied context.type if available -----------
        if context.type is not None:
            dt = context.type
            urgency = _URGENCY_BY_TYPE.get(dt, UrgencyLevel.P2)
            # Even when type is supplied, we still do keyword matching to
            # compute a confidence score and to enrich the reasoning.
            typed_keywords = self._keywords_for_type(dt)
            match_count = _count_matches(text, typed_keywords) if typed_keywords else 0
            confidence = _confidence_for_match_count(match_count) if match_count > 0 else 0.6

            # If the supplied type doesn't match any keywords, lower confidence
            if match_count == 0:
                confidence = 0.5

            return ClassificationResult(
                dispute_type=dt,
                urgency=urgency,
                requires_human=False,
                confidence=confidence,
                reasoning=(
                    f"Dispute type was pre-supplied as '{dt.value}'. "
                    f"Keyword matching found {match_count} supporting keyword(s). "
                    f"Urgency set to {urgency.value} based on the dispute type."
                ),
            )

        # -- Step 3: Keyword-based classification -----------
        best_type: Optional[DisputeType] = None
        best_count = 0
        best_keywords: list[str] = []

        for dt, keywords, urgency in _TYPE_RULES:
            if dt == DisputeType.ACCIDENT:
                continue  # already handled in P0 check
            count = _count_matches(text, keywords)
            if count > best_count:
                best_type = dt
                best_count = count
                best_keywords = [kw for kw in keywords if kw in text]

        # -- Step 4: Unknown / ambiguous fallback -----------
        if best_type is None or best_count == 0:
            return ClassificationResult(
                dispute_type=None,
                urgency=UrgencyLevel.P3,
                requires_human=True,
                confidence=0.3,
                reasoning=(
                    "No keywords matched any known dispute type. The input is "
                    "ambiguous or does not fit any defined category. "
                    "Requires human review for manual classification."
                ),
            )

        confidence = _confidence_for_match_count(best_count)
        urgency = _URGENCY_BY_TYPE.get(best_type, UrgencyLevel.P2)

        return ClassificationResult(
            dispute_type=best_type,
            urgency=urgency,
            requires_human=False,
            confidence=confidence,
            reasoning=(
                f"Matched {best_count} keyword(s) for '{best_type.value}' "
                f"({', '.join(best_keywords[:3])}). Classified as {urgency.value} "
                f"urgency. No P0 safety keywords were detected."
            ),
        )

    @staticmethod
    def _keywords_for_type(dt: DisputeType) -> list[str]:
        """Return the keyword list associated with a given dispute type."""
        mapping = {
            DisputeType.ROUTE_DEVIATION: _ROUTE_KEYWORDS,
            DisputeType.NO_SHOW: _NO_SHOW_KEYWORDS,
            DisputeType.FARE: _FARE_KEYWORDS,
            DisputeType.CANCELLATION: _CANCELLATION_KEYWORDS,
            DisputeType.SERVICE_QUALITY: _SERVICE_KEYWORDS,
            DisputeType.DELIVERY: _DELIVERY_KEYWORDS,
            DisputeType.DRIVER_RIGHTS: _DRIVER_RIGHTS_KEYWORDS,
            DisputeType.ACCIDENT: _P0_KEYWORDS,
        }
        return mapping.get(dt, [])
