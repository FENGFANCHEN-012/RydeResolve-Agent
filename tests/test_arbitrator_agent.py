"""
Tests for the ArbitrationAgent.

These tests verify:
1. The arbitrator correctly calls the LLM with all inputs.
2. Valid LLM JSON is parsed into a Decision.
3. Invalid / missing LLM responses fall back safely.
4. Policy reference sanitisation strips hallucinated refs.
"""
import json
import pytest

from src.agents.arbitrator import ArbitrationAgent, Decision, Verdict


class FakeLLMClient:
    """Mock LLM client that returns a predefined response."""

    def __init__(self, response_text: str, raise_error: bool = False):
        self._response = response_text
        self._raise = raise_error

    async def chat_json(self, messages, temperature=None):
        if self._raise:
            raise RuntimeError("Fake LLM error")
        return self._response


@pytest.fixture
def minimal_inputs():
    """Minimal valid inputs for arbitrate()."""
    return {
        "context": {"dispute_id": "D-001", "type": "route_deviation"},
        "passenger_analysis": {
            "stance": "Driver took a longer route.",
            "confidence": 0.8,
            "policy_references": ["terms_of_use#3"],
        },
        "driver_analysis": {
            "stance": "Traffic required the detour.",
            "confidence": 0.6,
            "policy_references": ["terms_of_use#3"],
        },
        "policy_evaluation": {
            "policies": [
                {
                    "source": "terms_of_use",
                    "chunk_index": 3,
                    "section": "Route policy",
                    "clause": "Drivers must follow the recommended route unless traffic conditions require a detour.",
                }
            ]
        },
        "debate_history": [],
    }


class TestArbitrationAgent:

    @pytest.mark.asyncio
    async def test_arbitrate_success(self, minimal_inputs):
        """Happy path: valid JSON → Decision with correct fields."""
        fake_response = json.dumps({
            "verdict": "partially_upheld",
            "confidence": 0.82,
            "refund_amount": 5.5,
            "compensation": "Apology message from driver",
            "driver_penalty": "Warning note on route compliance",
            "rationale": "GPS shows a 67% deviation with light traffic. Policy requires drivers to follow the recommended route.",
            "policy_references": ["terms_of_use#3"],
            "escalation_recommended": False,
            "human_review_needed": False,
        })
        agent = ArbitrationAgent(llm_client=FakeLLMClient(fake_response))
        decision = await agent.arbitrate(**minimal_inputs)

        assert isinstance(decision, Decision)
        assert decision.verdict == Verdict.PARTIALLY_UPHELD
        assert decision.confidence == pytest.approx(0.82)
        assert decision.refund_amount == pytest.approx(5.5)
        assert decision.compensation is not None
        assert decision.driver_penalty is not None
        assert "GPS" in decision.rationale
        assert decision.policy_references == ["terms_of_use#3"]
        assert decision.human_review_needed is False
        assert decision.escalation_recommended is False

    @pytest.mark.asyncio
    async def test_arbitrate_invalid_verdict_fallback(self, minimal_inputs):
        """Invalid verdict string → defaults to DISMISSED + human_review."""
        fake_response = json.dumps({
            "verdict": "banana",
            "confidence": 0.5,
            "rationale": "some reasoning",
            "policy_references": [],
        })
        agent = ArbitrationAgent(llm_client=FakeLLMClient(fake_response))
        decision = await agent.arbitrate(**minimal_inputs)

        assert decision.verdict == Verdict.DISMISSED
        assert decision.human_review_needed is True
        assert "invalid verdict" in decision.rationale.lower()

    @pytest.mark.asyncio
    async def test_arbitrate_llm_failure_fallback(self, minimal_inputs):
        """LLM raises → safe decision with human_review_needed=True."""
        agent = ArbitrationAgent(llm_client=FakeLLMClient("", raise_error=True))
        decision = await agent.arbitrate(**minimal_inputs)

        assert decision.human_review_needed is True
        assert decision.escalation_recommended is True
        assert "LLM call failed" in decision.rationale

    @pytest.mark.asyncio
    async def test_arbitrate_invalid_json_fallback(self, minimal_inputs):
        """LLM returns garbage → safe decision."""
        agent = ArbitrationAgent(llm_client=FakeLLMClient("not-json-at-all"))
        decision = await agent.arbitrate(**minimal_inputs)

        assert decision.human_review_needed is True
        assert "invalid JSON" in decision.rationale

    @pytest.mark.asyncio
    async def test_policy_reference_sanitisation(self, minimal_inputs):
        """Hallucinated policy refs are stripped and noted."""
        fake_response = json.dumps({
            "verdict": "partially_upheld",
            "confidence": 0.75,
            "rationale": "Driver deviated.",
            "policy_references": [
                "terms_of_use#3",          # valid
                "fake_policy#999",         # hallucinated → should be stripped
            ],
        })
        agent = ArbitrationAgent(llm_client=FakeLLMClient(fake_response))
        decision = await agent.arbitrate(**minimal_inputs)

        assert "terms_of_use#3" in decision.policy_references
        assert "fake_policy#999" not in decision.policy_references
        assert "unverified policy reference" in decision.rationale.lower()
        assert decision.human_review_needed is True

    @pytest.mark.asyncio
    async def test_low_confidence_triggers_human_review(self, minimal_inputs):
        """Confidence <= threshold → human_review_needed enforced."""
        fake_response = json.dumps({
            "verdict": "upheld",
            "confidence": 0.3,
            "rationale": "Weak evidence.",
            "policy_references": [],
        })
        agent = ArbitrationAgent(llm_client=FakeLLMClient(fake_response))
        decision = await agent.arbitrate(**minimal_inputs)

        assert decision.confidence == pytest.approx(0.3)
        assert decision.human_review_needed is True

    @pytest.mark.asyncio
    async def test_llm_client_none_fallback(self, minimal_inputs):
        """No LLM client → safe decision with human review flagged."""
        agent = ArbitrationAgent(llm_client=None)
        decision = await agent.arbitrate(**minimal_inputs)

        assert decision.human_review_needed is True
        assert decision.escalation_recommended is True
        # rationale should mention some kind of LLM failure (either
        # "not available" or a real API quota error in CI)
        assert "LLM" in decision.rationale

    # ------------------------------------------------------------------
    # JSON parsing edge cases
    # ------------------------------------------------------------------

    @pytest.mark.asyncio
    async def test_markdown_fence_stripping(self, minimal_inputs):
        """LLM wraps JSON in markdown fences → still parsed."""
        fake_response = (
            "```json\n"
            + json.dumps({
                "verdict": "dismissed",
                "confidence": 0.9,
                "rationale": "No deviation detected.",
                "policy_references": [],
            })
            + "\n```"
        )
        agent = ArbitrationAgent(llm_client=FakeLLMClient(fake_response))
        decision = await agent.arbitrate(**minimal_inputs)

        assert decision.verdict == Verdict.DISMISSED
        assert decision.confidence == pytest.approx(0.9)
