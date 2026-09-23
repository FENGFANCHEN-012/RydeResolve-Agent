"""
Tests for ClassifierAgent — hybrid approach: fast P0 keyword scan +
deterministic keyword classification + optional LLM classification.

All tests run offline without API keys, network, or ChromaDB.
LLM-based tests use AsyncMock / fake injected LLM clients.
"""
import json
import sys
from unittest.mock import AsyncMock

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


def make_mock_llm(response_text: str = "{}") -> AsyncMock:
    """Create a mock LLM client whose chat_json returns the given text."""
    llm = AsyncMock()
    llm.chat_json = AsyncMock(return_value=response_text)
    return llm


def make_mock_llm_exception(exc: Exception = RuntimeError("API timeout")) -> AsyncMock:
    """Create a mock LLM client whose chat_json raises an exception."""
    llm = AsyncMock()
    llm.chat_json = AsyncMock(side_effect=exc)
    return llm


def llm_response(
    dispute_type: str | None = None,
    urgency: str = "P2",
    requires_human: bool = False,
    confidence: float = 0.8,
    reasoning: str = "LLM classification.",
) -> str:
    """Build a JSON LLM response string."""
    return json.dumps({
        "dispute_type": dispute_type,
        "urgency": urgency,
        "requires_human": requires_human,
        "confidence": confidence,
        "reasoning": reasoning,
    })


# ---------------------------------------------------------------------------
# P0 Safety Keyword Tests (offline, no API key, no LLM)
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
# Offline Keyword Classification Tests (no API key, no LLM)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_keyword_route_deviation():
    """Route deviation keywords classify correctly without LLM."""
    agent = ClassifierAgent()
    ctx = make_context(
        "The driver took a longer route and deviated from the GPS. "
        "We went the wrong way and missed the exit. The fare was higher than estimated."
    )
    result = await agent.classify(ctx)

    assert result.dispute_type == DisputeType.ROUTE_DEVIATION
    assert result.confidence >= 0.65
    assert result.confidence <= 0.80
    assert result.requires_human is False


@pytest.mark.asyncio
async def test_keyword_no_show():
    """No-show keywords classify correctly without LLM."""
    agent = ClassifierAgent()
    ctx = make_context(
        "The driver never showed up. I waited at the pickup for 15 minutes "
        "but the driver didn't arrive. I was charged a cancellation fee."
    )
    result = await agent.classify(ctx)

    assert result.dispute_type == DisputeType.NO_SHOW
    assert result.confidence >= 0.65
    assert result.confidence <= 0.80
    assert result.requires_human is False


@pytest.mark.asyncio
async def test_keyword_fare_dispute():
    """Fare dispute keywords classify correctly without LLM."""
    agent = ClassifierAgent()
    ctx = make_context(
        "I was overcharged. The fare was S$25 but the app showed S$15 "
        "when I booked. There was a surge price I didn't agree to."
    )
    result = await agent.classify(ctx)

    assert result.dispute_type == DisputeType.FARE
    assert result.confidence >= 0.65
    assert result.confidence <= 0.80
    assert result.requires_human is False


@pytest.mark.asyncio
async def test_keyword_cancellation_refund():
    """Cancellation refund keywords classify correctly without LLM."""
    agent = ClassifierAgent()
    ctx = make_context(
        "I cancelled the ride within 2 minutes but was still charged a "
        "cancellation fee of S$5. The driver hadn't even been assigned yet. "
        "I want my refund."
    )
    result = await agent.classify(ctx)

    assert result.dispute_type == DisputeType.CANCELLATION
    assert result.confidence >= 0.65
    assert result.confidence <= 0.80
    assert result.requires_human is False


@pytest.mark.asyncio
async def test_keyword_service_quality():
    """Service quality keywords classify correctly without LLM."""
    agent = ClassifierAgent()
    ctx = make_context(
        "The driver was very rude and shouted at me. The car was dirty "
        "and smelled bad. He was speeding and driving recklessly."
    )
    result = await agent.classify(ctx)

    assert result.dispute_type == DisputeType.SERVICE_QUALITY
    assert result.confidence >= 0.65
    assert result.confidence <= 0.80
    assert result.requires_human is False


@pytest.mark.asyncio
async def test_keyword_driver_rights():
    """Driver rights keywords classify correctly without LLM."""
    agent = ClassifierAgent()
    ctx = make_context(
        "I am a driver and my account was wrongfully suspended. "
        "The rider falsely accused me of being rude. I want my account reinstated.",
        reporter="driver",
    )
    result = await agent.classify(ctx)

    assert result.dispute_type == DisputeType.DRIVER_RIGHTS
    assert result.confidence >= 0.65
    assert result.confidence <= 0.80
    assert result.requires_human is False


@pytest.mark.asyncio
async def test_keyword_delivery():
    """Delivery keywords classify correctly without LLM."""
    agent = ClassifierAgent()
    ctx = make_context(
        "My RydeSEND package was delivered to the wrong address. "
        "The item inside was broken. The delivery partner didn't follow instructions."
    )
    result = await agent.classify(ctx)

    assert result.dispute_type == DisputeType.DELIVERY
    assert result.confidence >= 0.65
    assert result.confidence <= 0.80
    assert result.requires_human is False


# ---------------------------------------------------------------------------
# Keyword Priority Tests
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_no_show_priority_over_cancellation_refund():
    """no_show should win over cancellation_refund when both match."""
    agent = ClassifierAgent()
    ctx = make_context(
        "The driver never arrived at the pickup. I waited 15 minutes "
        "and was charged a cancellation fee. I want a refund."
    )
    result = await agent.classify(ctx)

    assert result.dispute_type == DisputeType.NO_SHOW
    assert result.confidence >= 0.65


# ---------------------------------------------------------------------------
# P0 Override Tests
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_p0_overrides_normal_categories():
    """P0 safety keywords take priority over all other categories."""
    agent = ClassifierAgent()
    ctx = make_context(
        "The driver took a longer route AND then assaulted me. "
        "I was injured and need to go to hospital."
    )
    result = await agent.classify(ctx)

    # P0 safety check happens before keyword classification
    assert result.dispute_type == DisputeType.ACCIDENT
    assert result.urgency == UrgencyLevel.P0
    assert result.requires_human is True


# Ported from PR #3 (feature/classifier-agent)
@pytest.mark.asyncio
async def test_supplied_type_overridden_by_p0_safety():
    """Even if context.type is pre-supplied, a P0 safety keyword overrides it."""
    agent = ClassifierAgent()
    ctx = make_context(
        "There was an accident and the rider was injured.",
        type=DisputeType.ROUTE_DEVIATION,  # supplied type, but P0 detected
    )
    result = await agent.classify(ctx)

    assert result.dispute_type == DisputeType.ACCIDENT
    assert result.urgency == UrgencyLevel.P0
    assert result.requires_human is True


# ---------------------------------------------------------------------------
# Unknown / Safe Fallback Tests
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_unknown_input_safe_fallback():
    """Unknown input with no keywords and no API key produces safe fallback."""
    agent = ClassifierAgent()
    ctx = make_context("something vague and unclear")
    result = await agent.classify(ctx)

    assert result.dispute_type is None
    assert result.urgency == UrgencyLevel.P3
    assert result.confidence == 0.3
    assert result.requires_human is True


# ---------------------------------------------------------------------------
# Confidence Range Tests
# ---------------------------------------------------------------------------

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


# ---------------------------------------------------------------------------
# Injected Mock LLM Tests
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_injected_llm_route_deviation():
    """Injected mock LLM classifies route deviation correctly."""
    llm = make_mock_llm(llm_response(
        dispute_type="route_deviation",
        urgency="P1",
        confidence=0.85,
        requires_human=False,
    ))
    agent = ClassifierAgent(llm_client=llm)
    ctx = make_context("The driver took a weird route.")
    result = await agent.classify(ctx)

    assert result.dispute_type == DisputeType.ROUTE_DEVIATION
    assert result.urgency == UrgencyLevel.P1
    assert result.confidence == 0.85
    assert result.requires_human is False
    llm.chat_json.assert_awaited_once()


@pytest.mark.asyncio
async def test_injected_llm_invalid_json_falls_back():
    """Invalid JSON from injected LLM produces safe fallback."""
    llm = make_mock_llm("This is not JSON at all.")
    agent = ClassifierAgent(llm_client=llm)
    ctx = make_context("something ambiguous and unclear")
    result = await agent.classify(ctx)

    assert result.dispute_type is None
    assert result.urgency == UrgencyLevel.P3
    assert result.confidence == 0.3
    assert result.requires_human is True
    assert "invalid JSON" in result.reasoning or "failed" in result.reasoning.lower()


@pytest.mark.asyncio
async def test_injected_llm_exception_falls_back():
    """Exception from injected LLM produces safe fallback."""
    llm = make_mock_llm_exception(RuntimeError("API timeout"))
    agent = ClassifierAgent(llm_client=llm)
    ctx = make_context("something ambiguous and unclear")
    result = await agent.classify(ctx)

    assert result.dispute_type is None
    assert result.urgency == UrgencyLevel.P3
    assert result.confidence == 0.3
    assert result.requires_human is True
    assert "failed" in result.reasoning.lower() or "timeout" in result.reasoning.lower()


# ---------------------------------------------------------------------------
# Context Type Pre-Set Tests
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_context_type_preset_with_keyword_corroboration():
    """When context.type is set and keywords agree, confidence is boosted."""
    agent = ClassifierAgent()
    ctx = make_context(
        "The driver took a longer route and I was overcharged.",
        type=DisputeType.ROUTE_DEVIATION,
    )
    result = await agent.classify(ctx)

    assert result.dispute_type == DisputeType.ROUTE_DEVIATION
    assert result.confidence >= 0.75
    assert result.requires_human is False


@pytest.mark.asyncio
async def test_context_type_preset_without_keyword():
    """When context.type is set but no keywords match, still trust it."""
    agent = ClassifierAgent()
    ctx = make_context(
        "I have an issue with my trip.",
        type=DisputeType.FARE,
    )
    result = await agent.classify(ctx)

    assert result.dispute_type == DisputeType.FARE
    assert result.confidence >= 0.65


# ---------------------------------------------------------------------------
# Rich Context Test
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_rich_context_keyword_classification():
    """Rich context with trip and payment data should still classify via keywords."""
    agent = ClassifierAgent()
    ctx = make_context(
        "The fare was wrong and I was overcharged.",
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

    assert result.dispute_type == DisputeType.FARE
    assert result.confidence >= 0.65
