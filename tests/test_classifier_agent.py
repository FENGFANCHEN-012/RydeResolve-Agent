"""
Tests for ClassifierAgent — deterministic, offline, no API keys required.
"""
import sys

import pytest

sys.path.insert(0, ".")

from src.agents.classifier import ClassifierAgent, ClassificationResult, UrgencyLevel
from src.agents.collector import DisputeContext, DisputeType


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_context(description: str, **overrides) -> DisputeContext:
    defaults = dict(
        dispute_id="TEST-001",
        reporter="rider",
        order_id="RYDE-TEST-001",
        description=description,
    )
    defaults.update(overrides)
    return DisputeContext(**defaults)


# ---------------------------------------------------------------------------
# 1. Route deviation
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_route_deviation():
    agent = ClassifierAgent()
    ctx = make_context(
        "The driver took a longer route and deviated from the GPS. "
        "We went the wrong way and missed the exit."
    )
    result = await agent.classify(ctx)

    assert result.dispute_type == DisputeType.ROUTE_DEVIATION
    assert result.urgency == UrgencyLevel.P1
    assert result.requires_human is False
    assert result.confidence > 0.5
    assert "route" in result.reasoning.lower() or "route_deviation" in result.reasoning.lower()


# ---------------------------------------------------------------------------
# 2. No-show
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_no_show():
    agent = ClassifierAgent()
    ctx = make_context(
        "The driver never showed up. I waited at the pickup but the driver "
        "didn't arrive. Complete no-show."
    )
    result = await agent.classify(ctx)

    assert result.dispute_type == DisputeType.NO_SHOW
    assert result.urgency == UrgencyLevel.P1
    assert result.requires_human is False
    assert result.confidence > 0.5
    assert "no_show" in result.reasoning.lower() or "no-show" in result.reasoning.lower()


# ---------------------------------------------------------------------------
# 3. Fare dispute
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_fare_dispute():
    agent = ClassifierAgent()
    ctx = make_context(
        "I was overcharged. The fare was too expensive and I was charged more "
        "than the estimated amount. There was a surge price."
    )
    result = await agent.classify(ctx)

    assert result.dispute_type == DisputeType.FARE
    assert result.urgency == UrgencyLevel.P1
    assert result.requires_human is False
    assert result.confidence > 0.5
    assert "fare" in result.reasoning.lower()


# ---------------------------------------------------------------------------
# 4. Service quality
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_service_quality():
    agent = ClassifierAgent()
    ctx = make_context(
        "The driver was very rude and unprofessional. The car was dirty and "
        "smelly. Unsafe driving and speeding throughout the trip."
    )
    result = await agent.classify(ctx)

    assert result.dispute_type == DisputeType.SERVICE_QUALITY
    assert result.urgency == UrgencyLevel.P2
    assert result.requires_human is False
    assert result.confidence > 0.5
    assert "service_quality" in result.reasoning.lower() or "service" in result.reasoning.lower()


# ---------------------------------------------------------------------------
# 5. Accident / injury requiring human review (P0)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_accident_requires_human():
    agent = ClassifierAgent()
    ctx = make_context(
        "There was an accident and I was injured. The driver crashed into "
        "another car and I had to go to the hospital. Possible concussion."
    )
    result = await agent.classify(ctx)

    assert result.dispute_type == DisputeType.ACCIDENT
    assert result.urgency == UrgencyLevel.P0
    assert result.requires_human is True
    assert result.confidence > 0.5
    assert "P0" in result.reasoning
    assert "safety" in result.reasoning.lower() or "human" in result.reasoning.lower()


# ---------------------------------------------------------------------------
# 6. Unknown / ambiguous input fallback
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_unknown_input_fallback():
    agent = ClassifierAgent()
    ctx = make_context("I just didn't like it. It was not great overall.")
    result = await agent.classify(ctx)

    assert result.dispute_type is None
    assert result.requires_human is True
    assert result.confidence <= 0.5
    assert "ambiguous" in result.reasoning.lower() or "no keywords" in result.reasoning.lower()


# ---------------------------------------------------------------------------
# 7. Confidence range (always between 0.0 and 1.0)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_confidence_range():
    agent = ClassifierAgent()

    # Test several inputs and verify confidence is always in [0, 1]
    descriptions = [
        "accident injury crash",
        "longer route detour wrong way missed exit",
        "rude dirty unprofessional speeding",
        "something vague and unclear",
    ]
    for desc in descriptions:
        ctx = make_context(desc)
        result = await agent.classify(ctx)
        assert 0.0 <= result.confidence <= 1.0, (
            f"confidence {result.confidence} out of range for: {desc}"
        )

    # Also verify that the Pydantic validator clamps out-of-range values
    clamped = ClassificationResult(
        dispute_type=DisputeType.FARE,
        urgency=UrgencyLevel.P1,
        requires_human=False,
        confidence=5.0,
        reasoning="test",
    )
    assert clamped.confidence == 1.0

    clamped_low = ClassificationResult(
        dispute_type=DisputeType.FARE,
        urgency=UrgencyLevel.P1,
        requires_human=False,
        confidence=-1.0,
        reasoning="test",
    )
    assert clamped_low.confidence == 0.0


# ---------------------------------------------------------------------------
# 8. Supplied context.type is respected (unless P0 safety issue)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_supplied_context_type_respected():
    agent = ClassifierAgent()

    # When context.type is set and keywords support it, use the type
    ctx = make_context(
        "The driver took a longer route and deviated from the GPS.",
        type=DisputeType.ROUTE_DEVIATION,
    )
    result = await agent.classify(ctx)

    assert result.dispute_type == DisputeType.ROUTE_DEVIATION
    assert result.urgency == UrgencyLevel.P1
    assert result.requires_human is False
    assert result.confidence > 0.5
    assert "pre-supplied" in result.reasoning.lower() or "supplied" in result.reasoning.lower()


@pytest.mark.asyncio
async def test_supplied_type_overridden_by_p0_safety():
    """Even if context.type is set, a P0 safety keyword overrides it."""
    agent = ClassifierAgent()
    ctx = make_context(
        "There was an accident and the rider was injured.",
        type=DisputeType.ROUTE_DEVIATION,  # supplied type, but P0 detected
    )
    result = await agent.classify(ctx)

    assert result.dispute_type == DisputeType.ACCIDENT
    assert result.urgency == UrgencyLevel.P0
    assert result.requires_human is True
    assert "P0" in result.reasoning


@pytest.mark.asyncio
async def test_supplied_type_no_keyword_match():
    """When type is supplied but description has no matching keywords,
    confidence should be <= 0.5."""
    agent = ClassifierAgent()
    ctx = make_context(
        "Something happened during the trip.",
        type=DisputeType.FARE,
    )
    result = await agent.classify(ctx)

    assert result.dispute_type == DisputeType.FARE
    assert result.confidence <= 0.5
