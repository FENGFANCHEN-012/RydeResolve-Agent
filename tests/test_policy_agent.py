"""
Tests for PolicyAgent — all tests use mocks; no API keys, internet, or
running ChromaDB server are required.
"""
import json
import sys
from unittest.mock import AsyncMock, MagicMock

import pytest

sys.path.insert(0, ".")

from src.agents.collector import DisputeContext, DisputeType
from src.agents.policy import PolicyAgent


# ---------------------------------------------------------------------------
# Fixtures and helpers
# ---------------------------------------------------------------------------

SAMPLE_CLAUSES = [
    {
        "clause": "Drivers must take the most efficient route unless the rider "
        "agrees to a deviation or road conditions require it.",
        "source": "driver_guidelines.md",
        "section": "Route Compliance",
        "file_type": ".md",
        "similarity": 0.92,
        "chunk_index": 3,
    },
    {
        "clause": "If a driver is a no-show, the rider is entitled to a full "
        "refund of any cancellation charge.",
        "source": "cancellation_policy.md",
        "section": "No-Show",
        "file_type": ".md",
        "similarity": 0.88,
        "chunk_index": 1,
    },
]


def make_context(**overrides) -> DisputeContext:
    """Create a DisputeContext with sensible defaults."""
    defaults = dict(
        dispute_id="TEST-001",
        type=DisputeType.FARE,
        reporter="rider",
        order_id="RYDE-TEST-001",
        description="The driver took a longer route and overcharged me.",
        trip={"estimated_distance_km": 8.0, "actual_distance_km": 10.0},
        payment={"currency": "SGD", "charged_fare": 18.0, "estimated_fare": 14.0},
        chat_log=["Why are we going this way?", "Sorry, I missed the exit."],
        gps_trace=[{"lat": 1.31, "lng": 103.78}],
    )
    defaults.update(overrides)
    return DisputeContext(**defaults)


def make_mock_retriever(clauses: list[dict] | None = None) -> MagicMock:
    """Create a mock DocumentRetriever."""
    retriever = MagicMock()
    retriever.retrieve_for_dispute.return_value = clauses if clauses is not None else []
    return retriever


def make_mock_llm(response_text: str = "{}") -> AsyncMock:
    """Create a mock LLMClient whose chat_json returns the given text."""
    llm = AsyncMock()
    llm.chat_json = AsyncMock(return_value=response_text)
    return llm


# ---------------------------------------------------------------------------
# retrieve_policies tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_retrieve_policies_success():
    """Successful policy retrieval returns the clauses from the retriever."""
    retriever = make_mock_retriever(SAMPLE_CLAUSES)
    agent = PolicyAgent(retriever=retriever, llm_client=make_mock_llm())

    context = make_context()
    result = await agent.retrieve_policies(context)

    assert result == SAMPLE_CLAUSES
    assert len(result) == 2
    retriever.retrieve_for_dispute.assert_called_once()
    call_kwargs = retriever.retrieve_for_dispute.call_args.kwargs
    assert call_kwargs["dispute_type"] == DisputeType.FARE.value
    assert "longer route" in call_kwargs["dispute_description"]


@pytest.mark.asyncio
async def test_retrieve_policies_missing_dispute_type():
    """When dispute type is None, retrieval should still work with empty string."""
    retriever = make_mock_retriever(SAMPLE_CLAUSES)
    agent = PolicyAgent(retriever=retriever, llm_client=make_mock_llm())

    context = make_context(type=None)
    result = await agent.retrieve_policies(context)

    assert result == SAMPLE_CLAUSES
    call_kwargs = retriever.retrieve_for_dispute.call_args.kwargs
    assert call_kwargs["dispute_type"] == ""


@pytest.mark.asyncio
async def test_retrieve_policies_chromadb_unavailable():
    """If the retriever raises, retrieve_policies returns an empty list."""
    retriever = make_mock_retriever()
    retriever.retrieve_for_dispute.side_effect = ConnectionError("ChromaDB down")
    agent = PolicyAgent(retriever=retriever, llm_client=make_mock_llm())

    context = make_context()
    result = await agent.retrieve_policies(context)

    assert result == []


@pytest.mark.asyncio
async def test_retrieve_policies_no_retriever_returns_empty():
    """If retriever cannot be initialised, returns empty list gracefully."""
    agent = PolicyAgent(retriever=None, llm_client=make_mock_llm())
    # Patch _get_retriever to simulate failure
    agent._get_retriever = lambda: None

    context = make_context()
    result = await agent.retrieve_policies(context)

    assert result == []


# ---------------------------------------------------------------------------
# evaluate_compliance tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_evaluate_compliance_success():
    """Successful compliance evaluation returns all required keys from the LLM."""
    llm_response = json.dumps(
        {
            "passenger_compliant": True,
            "driver_compliant": False,
            "violations": ["Driver deviated from the optimal route."],
            "policy_references": ["driver_guidelines.md#3"],
            "reasoning": "The driver took a longer route without rider consent, "
            "violating the route compliance clause.",
            "confidence": 0.85,
            "requires_human_review": False,
        }
    )
    retriever = make_mock_retriever(SAMPLE_CLAUSES)
    llm = make_mock_llm(llm_response)
    agent = PolicyAgent(retriever=retriever, llm_client=llm)

    context = make_context()
    result = await agent.evaluate_compliance(context)

    assert result["passenger_compliant"] is True
    assert result["driver_compliant"] is False
    assert "Driver deviated from the optimal route." in result["violations"]
    assert result["policy_references"] == ["driver_guidelines.md#3"]
    assert result["confidence"] == 0.85
    assert result["requires_human_review"] is False
    assert "longer route" in result["reasoning"]
    llm.chat_json.assert_awaited_once()


@pytest.mark.asyncio
async def test_evaluate_compliance_no_policies_found():
    """When no policies are retrieved, returns a safe human-review result."""
    retriever = make_mock_retriever([])
    llm = make_mock_llm()
    agent = PolicyAgent(retriever=retriever, llm_client=llm)

    context = make_context()
    result = await agent.evaluate_compliance(context)

    assert result["requires_human_review"] is True
    assert result["passenger_compliant"] is None
    assert result["driver_compliant"] is None
    assert result["violations"] == []
    assert result["policy_references"] == []
    assert result["confidence"] == 0.0
    assert "No policy clauses" in result["reasoning"]
    # LLM should not be called when there are no policies
    llm.chat_json.assert_not_awaited()


@pytest.mark.asyncio
async def test_evaluate_compliance_invalid_llm_json():
    """If the LLM returns invalid JSON, return a safe human-review result."""
    retriever = make_mock_retriever(SAMPLE_CLAUSES)
    llm = make_mock_llm("This is not JSON at all.")
    agent = PolicyAgent(retriever=retriever, llm_client=llm)

    context = make_context()
    result = await agent.evaluate_compliance(context)

    assert result["requires_human_review"] is True
    assert result["confidence"] == 0.0
    assert "invalid JSON" in result["reasoning"]
    assert result["policy_references"] == []


@pytest.mark.asyncio
async def test_evaluate_compliance_llm_exception():
    """If the LLM call raises an exception, return a safe human-review result."""
    retriever = make_mock_retriever(SAMPLE_CLAUSES)
    llm = AsyncMock()
    llm.chat_json = AsyncMock(side_effect=RuntimeError("API timeout"))
    agent = PolicyAgent(retriever=retriever, llm_client=llm)

    context = make_context()
    result = await agent.evaluate_compliance(context)

    assert result["requires_human_review"] is True
    assert result["confidence"] == 0.0
    assert "LLM call failed" in result["reasoning"]
    assert result["policy_references"] == []


@pytest.mark.asyncio
async def test_evaluate_compliance_rejects_fabricated_policy_references():
    """Policy references not in retrieved clauses must be stripped and flagged."""
    llm_response = json.dumps(
        {
            "passenger_compliant": False,
            "driver_compliant": True,
            "violations": ["Rider was unresponsive."],
            "policy_references": [
                "driver_guidelines.md#3",          # valid – in SAMPLE_CLAUSES
                "fake_policy.md#99",               # fabricated – not in SAMPLE_CLAUSES
                "nonexistent.md#0",                # fabricated – not in SAMPLE_CLAUSES
            ],
            "reasoning": "Some reasoning here.",
            "confidence": 0.7,
            "requires_human_review": False,
        }
    )
    retriever = make_mock_retriever(SAMPLE_CLAUSES)
    llm = make_mock_llm(llm_response)
    agent = PolicyAgent(retriever=retriever, llm_client=llm)

    context = make_context()
    result = await agent.evaluate_compliance(context)

    # Only the valid reference should remain
    assert result["policy_references"] == ["driver_guidelines.md#3"]
    # Because references were dropped, human review should be triggered
    assert result["requires_human_review"] is True
    assert "unverified" in result["reasoning"]


@pytest.mark.asyncio
async def test_evaluate_compliance_markdown_fenced_json():
    """LLM output wrapped in markdown code fences should still parse."""
    llm_response = (
        "```json\n"
        + json.dumps(
            {
                "passenger_compliant": True,
                "driver_compliant": False,
                "violations": ["Excessive fare charged."],
                "policy_references": ["cancellation_policy.md#1"],
                "reasoning": "Driver overcharged the rider.",
                "confidence": 0.8,
                "requires_human_review": False,
            }
        )
        + "\n```"
    )
    retriever = make_mock_retriever(SAMPLE_CLAUSES)
    llm = make_mock_llm(llm_response)
    agent = PolicyAgent(retriever=retriever, llm_client=llm)

    context = make_context()
    result = await agent.evaluate_compliance(context)

    assert result["passenger_compliant"] is True
    assert result["driver_compliant"] is False
    assert result["policy_references"] == ["cancellation_policy.md#1"]
    assert result["requires_human_review"] is False


@pytest.mark.asyncio
async def test_evaluate_compliance_missing_keys_defaults():
    """LLM JSON missing some keys should get safe defaults, not crash."""
    llm_response = json.dumps(
        {
            "passenger_compliant": True,
            "driver_compliant": False,
        }
    )
    retriever = make_mock_retriever(SAMPLE_CLAUSES)
    llm = make_mock_llm(llm_response)
    agent = PolicyAgent(retriever=retriever, llm_client=llm)

    context = make_context()
    result = await agent.evaluate_compliance(context)

    assert result["passenger_compliant"] is True
    assert result["driver_compliant"] is False
    assert result["violations"] == []
    assert result["policy_references"] == []
    # Missing confidence + requires_human_review → safe defaults
    assert result["confidence"] == 0.0
    assert result["requires_human_review"] is True
