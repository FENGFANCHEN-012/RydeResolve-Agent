"""
Tests for ClassifierAgent — hybrid approach: fast P0 keyword scan + LLM classification.

P0 safety tests run offline without API keys.
LLM-based tests require a valid GEMINI_API_KEY environment variable.
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
# P0 Safety Keyword Tests (offline, no API key needed)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_p0_accident_keyword():
    """P0 keywords trigger instant classification without LLM."""
    agent = ClassifierAgent()
    ctx = make_context(
        "There was an accident and I was injured. The driver crashed into "
        "another car and I had to go to the hospital."
    )
    result = await agent.classify(ctx)

    assert result.dispute_type == DisputeType.ACCIDENT
    assert result.urgency == UrgencyLevel.P0
    assert result.requires_human is True
    assert result.confidence > 0.5
    assert "P0" in result.reasoning or "safety" in result.reasoning.lower()


@pytest.mark.asyncio
async def test_p0_assault_keyword():
    """Assault-related keywords trigger P0."""
    agent = ClassifierAgent()
    ctx = make_context(
        "The driver physically assaulted me and threatened to hurt me. "
        "I am calling the police."
    )
    result = await agent.classify(ctx)

    assert result.dispute_type == DisputeType.ACCIDENT
    assert result.urgency == UrgencyLevel.P0
    assert result.requires_human is True


@pytest.mark.asyncio
async def test_p0_harassment_keyword():
    """Harassment keywords trigger P0."""
    agent = ClassifierAgent()
    ctx = make_context(
        "The driver sexually harassed me during the trip. I felt unsafe."
    )
    result = await agent.classify(ctx)

    assert result.dispute_type == DisputeType.ACCIDENT
    assert result.urgency == UrgencyLevel.P0
    assert result.requires_human is True


# ---------------------------------------------------------------------------
# LLM-Based Classification Tests (require GEMINI_API_KEY)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_llm_route_deviation():
    """LLM should classify route deviation correctly."""
    agent = ClassifierAgent()
    ctx = make_context(
        "The driver took a longer route and deviated from the GPS. "
        "We went the wrong way and missed the exit. The fare was higher than estimated."
    )
    result = await agent.classify(ctx)

    assert result.dispute_type == DisputeType.ROUTE_DEVIATION
    assert result.urgency in (UrgencyLevel.P1, UrgencyLevel.P2)
    assert result.confidence > 0.5
    assert result.requires_human is False


@pytest.mark.asyncio
async def test_llm_no_show():
    """LLM should classify no-show correctly."""
    agent = ClassifierAgent()
    ctx = make_context(
        "The driver never showed up. I waited at the pickup for 15 minutes "
        "but the driver didn't arrive. I was charged a cancellation fee."
    )
    result = await agent.classify(ctx)

    assert result.dispute_type == DisputeType.NO_SHOW
    assert result.urgency in (UrgencyLevel.P1, UrgencyLevel.P2)
    assert result.confidence > 0.5


@pytest.mark.asyncio
async def test_llm_fare_dispute():
    """LLM should classify fare dispute correctly."""
    agent = ClassifierAgent()
    ctx = make_context(
        "I was overcharged. The fare was S$25 but the app showed S$15 "
        "when I booked. There was a surge price I didn't agree to."
    )
    result = await agent.classify(ctx)

    assert result.dispute_type == DisputeType.FARE
    assert result.urgency in (UrgencyLevel.P1, UrgencyLevel.P2)
    assert result.confidence > 0.5


@pytest.mark.asyncio
async def test_llm_cancellation_refund():
    """LLM should classify cancellation refund correctly."""
    agent = ClassifierAgent()
    ctx = make_context(
        "I cancelled the ride within 2 minutes but was still charged S$5. "
        "The driver hadn't even been assigned yet. I want my refund."
    )
    result = await agent.classify(ctx)

    assert result.dispute_type == DisputeType.CANCELLATION
    assert result.confidence > 0.5


@pytest.mark.asyncio
async def test_llm_service_quality():
    """LLM should classify service quality correctly."""
    agent = ClassifierAgent()
    ctx = make_context(
        "The driver was very rude and shouted at me. The car was dirty "
        "and smelled bad. He was speeding and driving recklessly."
    )
    result = await agent.classify(ctx)

    assert result.dispute_type == DisputeType.SERVICE_QUALITY
    assert result.urgency in (UrgencyLevel.P1, UrgencyLevel.P2, UrgencyLevel.P3)
    assert result.confidence > 0.5


@pytest.mark.asyncio
async def test_llm_driver_rights():
    """LLM should classify driver rights dispute correctly."""
    agent = ClassifierAgent()
    ctx = make_context(
        "I am a driver and my account was wrongfully suspended. "
        "The rider falsely accused me of being rude. I want my account reinstated.",
        reporter="driver",
    )
    result = await agent.classify(ctx)

    assert result.dispute_type == DisputeType.DRIVER_RIGHTS
    assert result.confidence > 0.5


@pytest.mark.asyncio
async def test_llm_delivery_dispute():
    """LLM should classify delivery dispute correctly."""
    agent = ClassifierAgent()
    ctx = make_context(
        "My RydeSEND package was delivered to the wrong address. "
        "The item inside was broken. The delivery partner didn't follow instructions."
    )
    result = await agent.classify(ctx)

    assert result.dispute_type == DisputeType.DELIVERY
    assert result.confidence > 0.5


# ---------------------------------------------------------------------------
# Edge Cases
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_p0_overrides_llm():
    """Even if description sounds like another type, P0 keywords take priority."""
    agent = ClassifierAgent()
    ctx = make_context(
        "The driver took a longer route AND then assaulted me. "
        "I was injured and need to go to hospital."
    )
    result = await agent.classify(ctx)

    # P0 safety check happens before LLM, so this should be ACCIDENT/P0
    assert result.dispute_type == DisputeType.ACCIDENT
    assert result.urgency == UrgencyLevel.P0
    assert result.requires_human is True


@pytest.mark.asyncio
async def test_confidence_range():
    """Confidence must always be in [0, 1]."""
    agent = ClassifierAgent()

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

    # Verify Pydantic validator clamps out-of-range values
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


@pytest.mark.asyncio
async def test_rich_context_improves_classification():
    """Providing more context (trip, payment, chat) should help LLM classify better."""
    agent = ClassifierAgent()
    ctx = make_context(
        "The fare was wrong.",
        trip={
            "pickup": "Orchard Road",
            "dropoff": "Changi Airport",
            "estimated_distance_km": 20.5,
            "actual_distance_km": 20.5,
        },
        payment={
            "estimated_fare": 28.0,
            "charged_fare": 45.0,
            "currency": "SGD",
        },
    )
    result = await agent.classify(ctx)

    # With rich context, should still classify as fare dispute
    assert result.dispute_type == DisputeType.FARE
    assert result.confidence > 0.5
