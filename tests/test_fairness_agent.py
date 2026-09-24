"""
Tests for the FairnessAgent.

All tests run offline:
  * No API keys or network calls required.
  * The LLMClient is replaced with ``FakeLLMClient`` (deterministic JSON).
  * Deterministic checks are exercised explicitly.
  * Output is validated as a structured ``FairnessAssessment``.

These tests verify the contract that the teammate integrating the agent
after the Arbitrator (in LangGraph) can rely on:
  - input shape      : ``FairnessAssessmentInput``
  - output shape     : ``FairnessAssessment``
  - safety guarantees: never raises; on any error returns
                        ``requires_human_review=True`` and
                        ``recommendation=ESCALATE``.
"""
from __future__ import annotations

import sys
from copy import deepcopy

import pytest

sys.path.insert(0, ".")

from src.agents.arbitrator import Decision, Verdict
from src.agents.fairness import (
    FairnessAgent,
    FairnessAssessment,
    FairnessAuditDetail,
    FairnessIssueCode,
    FairnessIssueDetail,
    FairnessRecommendation,
)
from src.models.dispute_state import FairnessAssessmentInput


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


class FakeLLMClient:
    """Deterministic LLM stand-in. Returns the configured JSON verbatim,
    or raises when configured to do so."""

    def __init__(self, response_text: str = "", raise_error: bool = False, gibberish: bool = False):
        self._response = response_text
        self._raise = raise_error
        self._gibberish = gibberish

    async def chat_json(self, messages, temperature=None):
        if self._raise:
            raise RuntimeError("Fake LLM error")
        if self._gibberish:
            return "not-json-at-all"
        return self._response


class SpyLLM(FakeLLMClient):
    """Records how many times the LLM was called."""

    def __init__(self):
        super().__init__()
        self.calls = 0

    async def chat_json(self, messages, temperature=None):
        self.calls += 1
        return "{}"


def make_decision(**overrides) -> Decision:
    defaults = dict(
        verdict=Verdict.PARTIALLY_UPHELD,
        confidence=0.85,
        rationale=(
            "GPS trace shows a 30% deviation from the recommended route; chat "
            "log corroborates the rider's complaint. Policy requires drivers "
            "to follow the recommended route unless traffic conditions require "
            "a detour."
        ),
        refund_amount=5.0,
        compensation="Apology voucher",
        driver_penalty="warning",
        policy_references=["terms_of_use#3"],
        escalation_recommended=False,
        human_review_needed=False,
    )
    defaults.update(overrides)
    return Decision(**defaults)


def make_passenger_analysis(**overrides) -> dict:
    defaults = dict(
        stance="Driver took a longer route.",
        evidence=[
            "GPS shows 30% deviation",
            "Chat message: 'Why are we going this way?'",
            "Payment shows $18.20 instead of estimated $14.50",
        ],
        contradictory_evidence=[],
        missing_evidence=[],
        obligations=["Payment of fare"],
        remedy_requested="Partial refund",
        policy_references=["terms_of_use#3"],
        reasoning="GPS + chat evidence supports a partial refund.",
        confidence=0.82,
        requires_human_review=False,
    )
    defaults.update(overrides)
    return defaults


def make_driver_analysis(**overrides) -> dict:
    defaults = dict(
        stance="Traffic required the detour.",
        evidence=[
            "Chat message: 'Sorry, I missed the exit.'",
        ],
        contradictory_evidence=[],
        missing_evidence=["No traffic data uploaded"],
        obligations=["Take most efficient route"],
        remedy_requested="No penalty",
        policy_references=["terms_of_use#3"],
        reasoning="Driver explained the route deviation.",
        confidence=0.60,
        requires_human_review=False,
    )
    defaults.update(overrides)
    return defaults


def make_policy_evaluation(**overrides) -> dict:
    defaults = dict(
        passenger_compliant=True,
        driver_compliant=False,
        violations=["Driver deviated from recommended route."],
        policy_references=["terms_of_use#3"],
        reasoning="Driver is non-compliant on route policy.",
        confidence=0.75,
        requires_human_review=False,
        policies=[
            {
                "source": "terms_of_use",
                "chunk_index": 3,
                "section": "Route policy",
                "clause": "Drivers must follow the recommended route unless traffic "
                          "conditions require a detour.",
            },
        ],
    )
    defaults.update(overrides)
    return defaults


def make_context(**overrides) -> dict:
    defaults = dict(
        dispute_id="DSP-FAIR-001",
        type="route_deviation",
        reporter="rider",
        order_id="RYDE-FAIR-001",
        description="The driver took a longer route and overcharged me.",
        trip={
            "estimated_distance_km": 8.0,
            "actual_distance_km": 10.4,
            "route_deviation_percent": 30.0,
        },
        payment={
            "estimated_fare": 14.5,
            "charged_fare": 18.2,
            "disputed_amount": 3.7,
        },
        chat_log=[
            {"sender": "rider", "message": "Why are we going this way?"},
            {"sender": "driver", "message": "Sorry, I missed the exit."},
        ],
        evidence=[],
    )
    defaults.update(overrides)
    return defaults


def make_input(**overrides) -> FairnessAssessmentInput:
    payload = dict(
        dispute_id="DSP-FAIR-001",
        decision=make_decision(),
        passenger_analysis=make_passenger_analysis(),
        driver_analysis=make_driver_analysis(),
        policy_evaluation=make_policy_evaluation(),
        debate_history=[
            {"round": 0, "speaker": "passenger", "content": make_passenger_analysis()},
            {"round": 0, "speaker": "driver", "content": make_driver_analysis()},
            {"round": 0, "speaker": "policy", "content": make_policy_evaluation()},
        ],
        context=make_context(),
    )
    payload.update(overrides)
    return FairnessAssessmentInput(**payload)


# ---------------------------------------------------------------------------
# Schema / structural tests
# ---------------------------------------------------------------------------


class TestSchema:
    @pytest.mark.asyncio
    async def test_output_is_fairness_assessment_instance(self):
        agent = FairnessAgent(llm_client=FakeLLMClient())
        assessment = await agent.assess(make_input())
        assert isinstance(assessment, FairnessAssessment)

    @pytest.mark.asyncio
    async def test_required_top_level_fields_present(self):
        agent = FairnessAgent(llm_client=FakeLLMClient())
        assessment = await agent.assess(make_input())
        for key in (
            "fairness_passed",
            "confidence",
            "issues",
            "recommendation",
            "requires_human_review",
            "audit_details",
            "assessed_at",
            "reason",
        ):
            assert key in assessment.model_dump(), f"missing field: {key}"

    @pytest.mark.asyncio
    async def test_audit_details_has_all_keys(self):
        agent = FairnessAgent(llm_client=FakeLLMClient())
        assessment = await agent.assess(make_input())
        audit_keys = set(assessment.audit_details.model_dump().keys())
        expected = {
            "evidence_counts",
            "confidence_gap",
            "passenger_confidence",
            "driver_confidence",
            "decision_confidence",
            "policies_cited_in_decision",
            "policies_retrieved",
            "policies_uncited",
            "hallucinated_policy_refs",
            "policy_compliance_alignment",
            "rationale_length_chars",
            "rationale_cites_evidence",
            "passenger_passenger_compliant",
            "driver_passenger_compliant",
            "verdict",
            "semantic_review_used",
            "semantic_review_skipped_reason",
        }
        assert expected.issubset(audit_keys)

    @pytest.mark.asyncio
    async def test_confidence_is_within_unit_interval(self):
        agent = FairnessAgent(llm_client=FakeLLMClient())
        assessment = await agent.assess(make_input())
        assert 0.0 <= assessment.confidence <= 1.0

    def test_frozen_input_cannot_be_mutated(self):
        inp = make_input()
        with pytest.raises(Exception):
            inp.dispute_id = "other"  # type: ignore[misc]


# ---------------------------------------------------------------------------
# Clearly fair decision -> PROCEED
# ---------------------------------------------------------------------------


class TestProceedPath:
    @pytest.mark.asyncio
    async def test_clean_decision_proceeds(self):
        agent = FairnessAgent(llm_client=FakeLLMClient())
        assessment = await agent.assess(make_input())

        assert assessment.fairness_passed is True
        assert assessment.recommendation == FairnessRecommendation.PROCEED
        assert assessment.requires_human_review is False
        assert assessment.issues == [] or all(i.severity == "low" for i in assessment.issues)
        # Audit signals should reflect the symmetric case:
        assert assessment.audit_details.passenger_confidence == pytest.approx(0.82)
        assert assessment.audit_details.driver_confidence == pytest.approx(0.60)
        assert assessment.audit_details.confidence_gap == pytest.approx(0.22, abs=0.01)
        assert assessment.audit_details.hallucinated_policy_refs == []
        assert assessment.audit_details.verdict == "partially_upheld"
        # Reason string should be top-line positive.
        assert "appear" in assessment.reason.lower() or "ready" in assessment.reason.lower()


# ---------------------------------------------------------------------------
# Asymmetric evidence handling
# ---------------------------------------------------------------------------


class TestAsymmetricEvidence:
    @pytest.mark.asyncio
    async def test_empty_evidence_one_side_triggers_one_side_not_considered(self):
        # Driver gives 0 evidence -> only passenger side considered.
        strong_passenger = make_passenger_analysis(evidence=[
            "GPS evidence",
            "Chat evidence",
            "Payment receipt",
            "Photo of route deviation",
        ])
        empty_driver = make_driver_analysis(evidence=[])
        inp = make_input(
            passenger_analysis=strong_passenger,
            driver_analysis=empty_driver,
        )
        agent = FairnessAgent(llm_client=FakeLLMClient())
        assessment = await agent.assess(inp)

        codes = {i.code for i in assessment.issues}
        assert FairnessIssueCode.ONE_SIDE_NOT_CONSIDERED in codes

    @pytest.mark.asyncio
    async def test_moderate_evidence_gap_does_not_flag_one_side(self):
        # Both sides have evidence; one much larger than the other.
        passenger = make_passenger_analysis(evidence=["x1", "x2", "x3", "x4", "x5"])
        driver = make_driver_analysis(evidence=["y1"])
        inp = make_input(passenger_analysis=passenger, driver_analysis=driver)
        agent = FairnessAgent(llm_client=FakeLLMClient())
        assessment = await agent.assess(inp)

        codes = {i.code for i in assessment.issues}
        assert codes  # at least one finding
        assert assessment.audit_details.evidence_counts["passenger"] == 5
        assert assessment.audit_details.evidence_counts["driver"] == 1
        # No one-sided flag because both sides have at least 1 evidence item.
        assert FairnessIssueCode.ONE_SIDE_NOT_CONSIDERED not in codes


# ---------------------------------------------------------------------------
# Hallucinated / uncited policy references
# ---------------------------------------------------------------------------


class TestPolicyReferenceHandling:
    @pytest.mark.asyncio
    async def test_hallucinated_policy_ref_triggers_block(self):
        decision = make_decision(
            policy_references=["terms_of_use#3", "fake_policy#999"],
        )
        inp = make_input(decision=decision)
        agent = FairnessAgent(llm_client=FakeLLMClient())
        assessment = await agent.assess(inp)

        assert FairnessIssueCode.HALLUCINATED_POLICY_REFS in {
            i.code for i in assessment.issues
        }
        assert assessment.recommendation == FairnessRecommendation.BLOCK
        assert assessment.fairness_passed is False
        assert assessment.requires_human_review is True
        assert "fake_policy#999" in assessment.audit_details.hallucinated_policy_refs

    @pytest.mark.asyncio
    async def test_no_policy_support_when_retrieval_empty_but_decision_cites(self):
        policy = make_policy_evaluation(policies=[], policy_references=[])
        decision = make_decision(policy_references=["something#1"])
        inp = make_input(decision=decision, policy_evaluation=policy)
        agent = FairnessAgent(llm_client=FakeLLMClient())
        assessment = await agent.assess(inp)

        codes = {i.code for i in assessment.issues}
        assert FairnessIssueCode.NO_POLICY_SUPPORT in codes
        assert assessment.requires_human_review is True
        assert assessment.fairness_passed is False

    @pytest.mark.asyncio
    async def test_no_cited_refs_when_retrieval_exists_flags_no_policy_support(self):
        decision = make_decision(policy_references=[])
        inp = make_input(decision=decision)
        agent = FairnessAgent(llm_client=FakeLLMClient())
        assessment = await agent.assess(inp)

        codes = {i.code for i in assessment.issues}
        assert FairnessIssueCode.NO_POLICY_SUPPORT in codes
        assert assessment.requires_human_review is True


# ---------------------------------------------------------------------------
# Low decision confidence
# ---------------------------------------------------------------------------


class TestLowConfidence:
    @pytest.mark.asyncio
    async def test_low_arbitrator_confidence_forces_human_review(self):
        decision = make_decision(confidence=0.30)
        inp = make_input(decision=decision)
        agent = FairnessAgent(llm_client=FakeLLMClient())
        assessment = await agent.assess(inp)

        codes = {i.code for i in assessment.issues}
        assert FairnessIssueCode.LOW_DECISION_CONFIDENCE in codes
        assert assessment.recommendation == FairnessRecommendation.ESCALATE
        assert assessment.requires_human_review is True

    @pytest.mark.asyncio
    async def test_below_threshold_triggers_human_review(self):
        from src.config import CONFIDENCE_THRESHOLD_LOW

        decision = make_decision(confidence=CONFIDENCE_THRESHOLD_LOW - 0.01)
        inp = make_input(decision=decision)
        agent = FairnessAgent(llm_client=FakeLLMClient())
        assessment = await agent.assess(inp)

        assert assessment.requires_human_review is True


# ---------------------------------------------------------------------------
# Internal inconsistencies
# ---------------------------------------------------------------------------


class TestInternalInconsistency:
    @pytest.mark.asyncio
    async def test_verdict_upheld_with_passenger_noncompliant_is_inconsistent(self):
        # If passenger is non-compliant and driver is compliant, UPHELD
        # contradicts the compliance evaluation.
        decision = make_decision(verdict=Verdict.UPHELD)
        policy = make_policy_evaluation(
            passenger_compliant=False,
            driver_compliant=True,
        )
        inp = make_input(decision=decision, policy_evaluation=policy)
        agent = FairnessAgent(llm_client=FakeLLMClient())
        assessment = await agent.assess(inp)

        codes = {i.code for i in assessment.issues}
        assert FairnessIssueCode.INTERNAL_INCONSISTENCY in codes
        assert assessment.requires_human_review is True

    @pytest.mark.asyncio
    async def test_verdict_dismissed_with_driver_noncompliant_passenger_compliant_is_inconsistent(self):
        decision = make_decision(verdict=Verdict.DISMISSED)
        policy = make_policy_evaluation(
            passenger_compliant=True,
            driver_compliant=False,
        )
        inp = make_input(decision=decision, policy_evaluation=policy)
        agent = FairnessAgent(llm_client=FakeLLMClient())
        assessment = await agent.assess(inp)

        codes = {i.code for i in assessment.issues}
        assert FairnessIssueCode.INTERNAL_INCONSISTENCY in codes

    @pytest.mark.asyncio
    async def test_consistent_verdict_dismissed_with_both_compliant(self):
        decision = make_decision(verdict=Verdict.DISMISSED)
        policy = make_policy_evaluation(
            passenger_compliant=True,
            driver_compliant=True,
        )
        inp = make_input(decision=decision, policy_evaluation=policy)
        agent = FairnessAgent(llm_client=FakeLLMClient())
        assessment = await agent.assess(inp)

        codes = {i.code for i in assessment.issues}
        # No inconsistency should be flagged for symmetric compliance.
        assert FairnessIssueCode.INTERNAL_INCONSISTENCY not in codes


# ---------------------------------------------------------------------------
# Missing / malformed inputs
# ---------------------------------------------------------------------------


class TestMissingData:
    @pytest.mark.asyncio
    async def test_missing_required_inputs_returns_safe_assessment(self):
        # Pass a dict instead of a proper input — must NOT raise.
        agent = FairnessAgent(llm_client=FakeLLMClient())
        bad = {"dispute_id": "X"}  # missing decision
        assessment = await agent.assess(bad)  # type: ignore[arg-type]

        assert isinstance(assessment, FairnessAssessment)
        assert assessment.fairness_passed is False
        assert assessment.requires_human_review is True
        assert assessment.recommendation == FairnessRecommendation.ESCALATE
        assert len(assessment.issues) >= 1

    @pytest.mark.asyncio
    async def test_empty_evidence_both_sides_flags_escalation(self):
        passenger = make_passenger_analysis(evidence=[])
        driver = make_driver_analysis(evidence=[])
        inp = make_input(passenger_analysis=passenger, driver_analysis=driver)
        agent = FairnessAgent(llm_client=FakeLLMClient())
        assessment = await agent.assess(inp)

        codes = {i.code for i in assessment.issues}
        assert FairnessIssueCode.ONE_SIDE_NOT_CONSIDERED in codes
        assert assessment.requires_human_review is True

    @pytest.mark.asyncio
    async def test_very_short_rationale_flags_unsupported_reasoning(self):
        decision = make_decision(rationale="ok.")  # < 20 chars
        inp = make_input(decision=decision)
        agent = FairnessAgent(llm_client=FakeLLMClient())
        assessment = await agent.assess(inp)

        codes = {i.code for i in assessment.issues}
        assert FairnessIssueCode.UNSUPPORTED_REASONING in codes


# ---------------------------------------------------------------------------
# LLM failure modes
# ---------------------------------------------------------------------------


class TestLLMFailureModes:
    @pytest.mark.asyncio
    async def test_llm_raises_still_returns_safe_assessment(self):
        # LLM raised — deterministic checks should still produce a result.
        failing_llm = FakeLLMClient(raise_error=True)
        agent = FairnessAgent(llm_client=failing_llm)
        assessment = await agent.assess(make_input())
        assert isinstance(assessment, FairnessAssessment)
        assert assessment.audit_details.semantic_review_used is False

    @pytest.mark.asyncio
    async def test_llm_returns_garbage_does_not_corrupt_result(self):
        nonsense_llm = FakeLLMClient(gibberish=True)
        agent = FairnessAgent(llm_client=nonsense_llm)
        assessment = await agent.assess(make_input())
        assert isinstance(assessment, FairnessAssessment)
        assert assessment.audit_details.semantic_review_used is False


# ---------------------------------------------------------------------------
# Deterministic checks without an LLM (no client at all)
# ---------------------------------------------------------------------------


class TestDeterministicOnly:
    @pytest.mark.asyncio
    async def test_no_llm_client_at_all_still_works(self):
        agent = FairnessAgent(llm_client=None)
        decision = make_decision(policy_references=["fake#1"])
        inp = make_input(decision=decision)
        assessment = await agent.assess(inp)
        assert isinstance(assessment, FairnessAssessment)
        assert assessment.audit_details.semantic_review_used is False

    @pytest.mark.asyncio
    async def test_no_llm_call_when_severe_issues_already(self):
        # Inject a hallucinated ref AND a low confidence -> severe findings.
        decision = make_decision(
            confidence=0.10,
            policy_references=["fake_policy#999"],
        )
        inp = make_input(decision=decision)
        spy = SpyLLM()
        agent = FairnessAgent(llm_client=spy)
        assessment = await agent.assess(inp)
        assert spy.calls == 0
        assert assessment.audit_details.semantic_review_skipped_reason is not None


# ---------------------------------------------------------------------------
# LLM-provided semantic issues are honoured
# ---------------------------------------------------------------------------


class TestSemanticReviewIntegration:
    SEMANTIC_OK = (
        '{"issues": [{"code": "unsupported_reasoning", "severity": "medium", '
        '"description": "Rationale leans on passenger narrative; driver '
        'perspective is not addressed.", "evidence_refs": ["terms_of_use#3"], '
        '"recommended_action": "Re-balance rationale."}], '
        '"rationale_alignment": "partial"}'
    )

    @pytest.mark.asyncio
    async def test_semantic_review_used_and_issues_appended(self):
        # Build an input that is clean deterministically so the LLM layer
        # actually gets called.
        agent = FairnessAgent(llm_client=FakeLLMClient(self.SEMANTIC_OK))
        inp = make_input()
        assessment = await agent.assess(inp)
        assert assessment.audit_details.semantic_review_used is True
        codes = {i.code for i in assessment.issues}
        assert FairnessIssueCode.UNSUPPORTED_REASONING in codes

    @pytest.mark.asyncio
    async def test_invalid_issue_codes_from_llm_are_dropped(self):
        bad = (
            '{"issues": [{"code": "made_up_code", "severity": "high", '
            '"description": "x", "evidence_refs": [], '
            '"recommended_action": ""}], "rationale_alignment": "unknown"}'
        )
        agent = FairnessAgent(llm_client=FakeLLMClient(bad))
        inp = make_input()
        assessment = await agent.assess(inp)
        # No "made_up_code" should appear in the issues list.
        assert all(i.code != "made_up_code" for i in assessment.issues)

    @pytest.mark.asyncio
    async def test_semantic_review_unverifiable_refs_are_dropped(self):
        # The LLM returns a fabricated policy reference; agent must drop it.
        bad = (
            '{"issues": [{"code": "unsupported_reasoning", "severity": "medium", '
            '"description": "test", "evidence_refs": ["INJECTED#X"], '
            '"recommended_action": ""}], "rationale_alignment": "partial"}'
        )
        agent = FairnessAgent(llm_client=FakeLLMClient(bad))
        inp = make_input()
        assessment = await agent.assess(inp)
        for issue in assessment.issues:
            assert "INJECTED#X" not in issue.evidence_refs


# ---------------------------------------------------------------------------
# Recommendation enum coverage
# ---------------------------------------------------------------------------


class TestRecommendationEnum:
    def test_all_enum_values_present(self):
        values = {r.value for r in FairnessRecommendation}
        assert values == {"proceed", "escalate", "amend_recommended", "block"}

    @pytest.mark.asyncio
    async def test_block_recommendation_for_hallucinated(self):
        decision = make_decision(policy_references=["fake#1"])
        inp = make_input(decision=decision)
        agent = FairnessAgent(llm_client=FakeLLMClient())
        a = await agent.assess(inp)
        assert a.recommendation == FairnessRecommendation.BLOCK

    @pytest.mark.asyncio
    async def test_amend_recommended_for_medium_severity(self):
        # Driver evidence is heavily asymmetric but both sides present.
        passenger = make_passenger_analysis(
            evidence=[f"item-{i}" for i in range(8)],
            confidence=0.85,
        )
        driver = make_driver_analysis(evidence=["only-one"], confidence=0.78)
        decision = make_decision(confidence=0.90, policy_references=["terms_of_use#3"])
        policy = make_policy_evaluation(
            passenger_compliant=False,
            driver_compliant=False,  # aligned: both non-compliant -> consistent
        )
        inp = make_input(
            passenger_analysis=passenger,
            driver_analysis=driver,
            decision=decision,
            policy_evaluation=policy,
        )
        agent = FairnessAgent(llm_client=FakeLLMClient())
        a = await agent.assess(inp)
        assert a.recommendation == FairnessRecommendation.AMEND_RECOMMENDED


# ---------------------------------------------------------------------------
# Issue code enum coverage
# ---------------------------------------------------------------------------


class TestIssueCodeEnum:
    def test_all_required_codes_present(self):
        values = {c.value for c in FairnessIssueCode}
        required = {
            "asymmetric_evidence",
            "uncited_policy_refs",
            "hallucinated_policy_refs",
            "unsupported_reasoning",
            "internal_inconsistency",
            "low_decision_confidence",
            "one_side_not_considered",
            "no_policy_support",
            "large_confidence_gap",
        }
        assert required.issubset(values)


# ---------------------------------------------------------------------------
# Deterministic / LLM blending
# ---------------------------------------------------------------------------


class TestHybridBlend:
    @pytest.mark.asyncio
    async def test_high_severity_deterministic_blocks_llm(self):
        decision = make_decision(confidence=0.05, policy_references=["fake#1"])
        spy = SpyLLM()
        agent = FairnessAgent(llm_client=spy)
        assessment = await agent.assess(make_input(decision=decision))
        assert spy.calls == 0  # Not called due to severe deterministic findings
        assert assessment.recommendation == FairnessRecommendation.BLOCK

    @pytest.mark.asyncio
    async def test_semantic_layer_can_lower_passing_to_amend(self):
        semantic = (
            '{"issues": [{"code": "large_confidence_gap", '
            '"severity": "medium", '
            '"description": "Semantic review flags confidence-gap concern.", '
            '"evidence_refs": [], "recommended_action": ""}], '
            '"rationale_alignment": "partial"}'
        )
        agent = FairnessAgent(llm_client=FakeLLMClient(semantic))
        a = await agent.assess(make_input())
        assert a.recommendation == FairnessRecommendation.AMEND_RECOMMENDED
        assert a.fairness_passed is False


# ---------------------------------------------------------------------------
# Provenance / audit trail
# ---------------------------------------------------------------------------


class TestAuditTrail:
    @pytest.mark.asyncio
    async def test_assessed_at_is_iso_format(self):
        agent = FairnessAgent(llm_client=FakeLLMClient())
        assessment = await agent.assess(make_input())
        # ISO-8601: starts with YYYY-MM-DD
        assert assessment.assessed_at[:10].count("-") == 2

    @pytest.mark.asyncio
    async def test_audit_evidence_counts_match_inputs(self):
        passenger = make_passenger_analysis(evidence=["a", "b", "c"])
        driver = make_driver_analysis(evidence=["x", "y"])
        inp = make_input(passenger_analysis=passenger, driver_analysis=driver)
        agent = FairnessAgent(llm_client=FakeLLMClient())
        a = await agent.assess(inp)
        assert a.audit_details.evidence_counts == {"passenger": 3, "driver": 2}

    @pytest.mark.asyncio
    async def test_no_use_of_demographic_fields(self):
        # Inject profile/rating info; ensure they do NOT alter the result.
        passenger = make_passenger_analysis(evidence=[])
        driver = make_driver_analysis(evidence=["x"])
        context = make_context(
            rider_profile={"name": "Alice", "age": 30, "race": "X"},
            driver_profile={"name": "Bob", "age": 45, "race": "Y"},
            ratings={"rider_rating": 4.9, "driver_rating": 2.0},
        )
        inp1 = make_input(
            passenger_analysis=passenger,
            driver_analysis=driver,
            context=context,
        )
        inp2 = make_input(
            passenger_analysis=deepcopy(passenger),
            driver_analysis=deepcopy(driver),
            context={
                **context,
                "rider_profile": None,
                "driver_profile": None,
                "ratings": None,
            },
        )
        a1 = await FairnessAgent(llm_client=FakeLLMClient()).assess(inp1)
        a2 = await FairnessAgent(llm_client=FakeLLMClient()).assess(inp2)
        # The fairness outcome must not depend on demographic data.
        assert a1.fairness_passed == a2.fairness_passed
        assert a1.recommendation == a2.recommendation
        assert {i.code for i in a1.issues} == {i.code for i in a2.issues}
