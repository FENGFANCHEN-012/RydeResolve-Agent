"""
Tests for the LangGraph dispute-resolution workflow.

All tests run offline:
  * No API keys or network calls required.
  * Every agent is replaced with a deterministic stub that records calls,
    so the tests verify *routing* behaviour (which nodes run, which never
    run) rather than agent internals.

Verified contracts:
  - normal dispute: collector -> classifier -> debate -> arbitrator
    -> fairness(PROCEED) -> executor
  - classifier requires_human: debate/arbitrator/fairness/executor never run
  - fairness requires_human_review=True, or recommendation in
    {AMEND_RECOMMENDED, ESCALATE, BLOCK}: executor never runs
  - node failure: run completes safely, executor never runs
  - Orchestrator.resolve() keeps the legacy response shape
"""
from __future__ import annotations

import sys

import pytest

sys.path.insert(0, ".")

from src.agents.arbitrator import Decision, Verdict
from src.agents.classifier import ClassificationResult, UrgencyLevel
from src.agents.collector import DisputeContext, DisputeType
from src.agents.fairness import (
    FairnessAssessment,
    FairnessAuditDetail,
    FairnessRecommendation,
)
from src.core.orchestrator import Orchestrator
from src.core.workflow import build_dispute_graph
from src.core.workflow_state import (
    STATUS_ESCALATED,
    STATUS_FAILED,
    STATUS_RESOLVED,
)

# ---------------------------------------------------------------------------
# Fixtures / stub agents
# ---------------------------------------------------------------------------


def make_context(**overrides) -> DisputeContext:
    defaults = dict(
        dispute_id="DRP-RYDE-001",
        type=None,
        reporter="passenger",
        order_id="RYDE-001",
        description="Driver took a longer route and overcharged me.",
        trip={"actual_distance_km": 10.4},
        payment={"estimated_fare": 14.5, "total_fare": 18.2},
        chat_log=[{"sender": "rider", "message": "Why this way?"}],
        gps_trace=[{"lat": 1.3, "lng": 103.8}],
        rider_profile={"rating": 4.9},
        driver_profile={"rating": 4.7},
        evidence=[],
        language="en",
    )
    defaults.update(overrides)
    return DisputeContext(**defaults)


def make_classification(**overrides) -> ClassificationResult:
    defaults = dict(
        dispute_type=DisputeType.ROUTE_DEVIATION,
        urgency=UrgencyLevel.P1,
        requires_human=False,
        confidence=0.9,
        reasoning="Route deviation keywords matched.",
    )
    defaults.update(overrides)
    return ClassificationResult(**defaults)


def make_decision(**overrides) -> Decision:
    defaults = dict(
        verdict=Verdict.PARTIALLY_UPHELD,
        confidence=0.85,
        refund_amount=3.7,
        compensation="Voucher",
        driver_penalty="warning",
        rationale=(
            "GPS trace shows a route deviation and the chat log corroborates "
            "the rider's complaint; policy requires the recommended route."
        ),
        policy_references=["terms_of_use#3"],
        escalation_recommended=False,
        human_review_needed=False,
    )
    defaults.update(overrides)
    return Decision(**defaults)


def make_fairness(
    recommendation: FairnessRecommendation = FairnessRecommendation.PROCEED,
    requires_human_review: bool = False,
    fairness_passed: bool = True,
    **overrides,
) -> FairnessAssessment:
    defaults = dict(
        fairness_passed=fairness_passed,
        confidence=0.9,
        issues=[],
        recommendation=recommendation,
        requires_human_review=requires_human_review,
        audit_details=FairnessAuditDetail(
            evidence_counts={"passenger": 3, "driver": 1},
            confidence_gap=0.2,
            passenger_confidence=0.82,
            driver_confidence=0.62,
            decision_confidence=0.85,
            policies_cited_in_decision=["terms_of_use#3"],
            policies_retrieved=["terms_of_use#3"],
            policies_uncited=[],
            hallucinated_policy_refs=[],
            policy_compliance_alignment="aligned",
            rationale_length_chars=120,
            rationale_cites_evidence=True,
            passenger_passenger_compliant=True,
            driver_passenger_compliant=False,
            verdict="partially_upheld",
            semantic_review_used=False,
        ),
        assessed_at="2026-09-24T00:00:00+00:00",
        reason="Decision appears fair and ready to execute.",
    )
    defaults.update(overrides)
    return FairnessAssessment(**defaults)


def make_debate_history() -> list[dict]:
    passenger = {
        "stance": "Driver took a longer route.",
        "evidence": ["GPS deviation", "Chat message"],
        "confidence": 0.82,
    }
    driver = {
        "stance": "Traffic required the detour.",
        "evidence": ["Chat: 'Sorry, I missed the exit.'"],
        "confidence": 0.6,
    }
    policy = {
        "passenger_compliant": True,
        "driver_compliant": False,
        "policies": [{"source": "terms_of_use", "chunk_index": 3}],
    }
    return [
        {"round": 0, "speaker": "passenger", "content": passenger},
        {"round": 0, "speaker": "driver", "content": driver},
        {"round": 0, "speaker": "policy", "content": policy},
    ]


class StubCollector:
    def __init__(self, context: DisputeContext | None = None, raise_error: bool = False):
        self.context = context or make_context()
        self.raise_error = raise_error
        self.calls = 0

    async def collect(self, report_text, order_id, reporter, evidence, language):
        self.calls += 1
        if self.raise_error:
            raise RuntimeError("collector boom")
        return self.context


class StubClassifier:
    def __init__(self, classification: ClassificationResult | None = None, raise_error: bool = False):
        self.classification = classification or make_classification()
        self.raise_error = raise_error
        self.calls = 0

    async def classify(self, context):
        self.calls += 1
        if self.raise_error:
            raise RuntimeError("classifier boom")
        return self.classification


class StubDebate:
    def __init__(self, raise_error: bool = False):
        self.raise_error = raise_error
        self.calls = 0

    async def debate(self, context):
        self.calls += 1
        if self.raise_error:
            raise RuntimeError("debate boom")
        return make_debate_history()


class StubArbitrator:
    def __init__(self, decision: Decision | None = None, raise_error: bool = False):
        self.decision = decision or make_decision()
        self.raise_error = raise_error
        self.calls = 0

    async def arbitrate(self, context, passenger_analysis, driver_analysis,
                        policy_evaluation, debate_history):
        self.calls += 1
        if self.raise_error:
            raise RuntimeError("arbitrator boom")
        return self.decision


class StubFairness:
    def __init__(self, assessment: FairnessAssessment | None = None, raise_error: bool = False):
        self.assessment = assessment or make_fairness()
        self.raise_error = raise_error
        self.calls = 0
        self.last_input = None

    async def assess(self, input_payload):
        self.calls += 1
        self.last_input = input_payload
        if self.raise_error:
            raise RuntimeError("fairness boom")
        return self.assessment


class StubExecutor:
    def __init__(self, raise_error: bool = False, result: dict | None = None):
        self.raise_error = raise_error
        self.result = result
        self.calls = 0
        self.last_decision = None

    async def execute(self, decision, dispute_id, language=None):
        self.calls += 1
        self.last_decision = decision
        if self.raise_error:
            raise RuntimeError("executor boom")
        if self.result is not None:
            return self.result
        return {
            "dispute_id": dispute_id,
            "executed": True,
            "status": "executed",
            "notifications_sent": True,
            "actions_taken": ["Refund SGD 3.70 (simulated)"],
            "transaction_records": [],
            "notifications": [],
            "error": None,
        }


def build_graph(collector=None, classifier=None, debate=None, arbitrator=None,
                fairness=None, executor=None):
    return build_dispute_graph(
        collector=collector or StubCollector(),
        classifier=classifier or StubClassifier(),
        debate_engine=debate or StubDebate(),
        arbitrator=arbitrator or StubArbitrator(),
        fairness_agent=fairness or StubFairness(),
        executor=executor or StubExecutor(),
    )


def initial_state() -> dict:
    return {
        "report_text": "Driver took a longer route and overcharged me.",
        "order_id": "RYDE-001",
        "reporter": "passenger",
        "evidence": [],
        "language": "en",
    }


# ---------------------------------------------------------------------------
# Routing tests
# ---------------------------------------------------------------------------


class TestGraphRouting:
    @pytest.mark.asyncio
    async def test_normal_dispute_reaches_executor(self):
        executor = StubExecutor()
        graph = build_graph(executor=executor)
        final = await graph.ainvoke(initial_state())

        assert executor.calls == 1
        assert final["status"] == STATUS_RESOLVED
        assert final["execution"]["executed"] is True
        assert final["fairness"].recommendation == FairnessRecommendation.PROCEED
        assert final["decision"].verdict == Verdict.PARTIALLY_UPHELD
        assert final["classification"].requires_human is False

    @pytest.mark.asyncio
    async def test_classifier_requires_human_skips_everything_downstream(self):
        collector = StubCollector()
        classifier = StubClassifier(
            classification=make_classification(requires_human=True, urgency=UrgencyLevel.P0)
        )
        debate = StubDebate()
        arbitrator = StubArbitrator()
        fairness = StubFairness()
        executor = StubExecutor()

        graph = build_graph(
            collector=collector, classifier=classifier, debate=debate,
            arbitrator=arbitrator, fairness=fairness, executor=executor,
        )
        final = await graph.ainvoke(initial_state())

        assert classifier.calls == 1
        assert debate.calls == 0
        assert arbitrator.calls == 0
        assert fairness.calls == 0
        assert executor.calls == 0
        assert final["status"] == STATUS_ESCALATED
        assert final["human_review_reason"] == "Safety/legal issue requires human review"
        # Early exit still carries the classification for the audit trail.
        assert final["classification"].requires_human is True
        assert final["execution"] is None

    @pytest.mark.asyncio
    async def test_fairness_proceed_runs_executor(self):
        fairness = StubFairness(
            assessment=make_fairness(
                recommendation=FairnessRecommendation.PROCEED,
                requires_human_review=False,
            )
        )
        executor = StubExecutor()
        graph = build_graph(fairness=fairness, executor=executor)
        final = await graph.ainvoke(initial_state())

        assert fairness.calls == 1
        assert executor.calls == 1
        assert final["status"] == STATUS_RESOLVED

    @pytest.mark.asyncio
    async def test_arbitrator_human_review_flag_skips_executor_even_if_fairness_passes(self):
        arbitrator = StubArbitrator(decision=make_decision(human_review_needed=True))
        fairness = StubFairness(assessment=make_fairness())
        executor = StubExecutor()
        graph = build_graph(arbitrator=arbitrator, fairness=fairness, executor=executor)

        final = await graph.ainvoke(initial_state())

        assert fairness.calls == 1  # preserve the fairness audit for the reviewer
        assert executor.calls == 0
        assert final["status"] == STATUS_ESCALATED
        assert final["human_review_reason"] == "Arbitrator requested human review."
        assert final["execution"] is None

    @pytest.mark.asyncio
    async def test_executor_escalation_does_not_mark_case_resolved(self):
        executor = StubExecutor(result={"executed": False, "status": "escalated_to_human"})
        graph = build_graph(executor=executor)

        final = await graph.ainvoke(initial_state())

        assert final["status"] == STATUS_ESCALATED
        assert final["execution"]["executed"] is False
        assert final["human_review_reason"] == "Executor requested human review."

    @pytest.mark.asyncio
    async def test_executor_failure_does_not_mark_case_resolved(self):
        executor = StubExecutor(result={"executed": False, "status": "failed", "error": "refund simulation failed"})
        graph = build_graph(executor=executor)

        final = await graph.ainvoke(initial_state())

        assert final["status"] == STATUS_FAILED
        assert final["execution"]["executed"] is False
        assert final["error"]["node"] == "executor"

    @pytest.mark.asyncio
    async def test_fairness_requires_human_review_never_runs_executor(self):
        # e.g. LOW_DECISION_CONFIDENCE: recommendation stays PROCEED but the
        # human-review flag is set.
        fairness = StubFairness(
            assessment=make_fairness(
                recommendation=FairnessRecommendation.PROCEED,
                requires_human_review=True,
            )
        )
        executor = StubExecutor()
        graph = build_graph(fairness=fairness, executor=executor)
        final = await graph.ainvoke(initial_state())

        assert executor.calls == 0
        assert final["status"] == STATUS_ESCALATED
        assert final["human_review_reason"] == "Decision appears fair and ready to execute."
        # Audit trail preserved for the human reviewer.
        assert final["fairness"].requires_human_review is True
        assert final["decision"] is not None

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "recommendation",
        [
            FairnessRecommendation.AMEND_RECOMMENDED,
            FairnessRecommendation.ESCALATE,
            FairnessRecommendation.BLOCK,
        ],
        ids=["amend_recommended", "escalate", "block"],
    )
    async def test_fairness_non_proceed_recommendations_never_run_executor(
        self, recommendation
    ):
        fairness = StubFairness(
            assessment=make_fairness(
                recommendation=recommendation, requires_human_review=False
            )
        )
        executor = StubExecutor()
        graph = build_graph(fairness=fairness, executor=executor)
        final = await graph.ainvoke(initial_state())

        assert executor.calls == 0
        assert final["status"] == STATUS_ESCALATED
        assert final["fairness"].recommendation == recommendation

    @pytest.mark.asyncio
    async def test_fairness_agent_failure_is_safe(self):
        fairness = StubFairness(raise_error=True)
        executor = StubExecutor()
        graph = build_graph(fairness=fairness, executor=executor)
        final = await graph.ainvoke(initial_state())

        assert executor.calls == 0
        assert final["status"] == STATUS_FAILED
        assert final["error"]["node"] == "fairness_agent"
        assert final["human_review_reason"] is not None

    @pytest.mark.asyncio
    async def test_arbitrator_failure_is_safe(self):
        arbitrator = StubArbitrator(raise_error=True)
        fairness = StubFairness()
        executor = StubExecutor()
        graph = build_graph(arbitrator=arbitrator, fairness=fairness, executor=executor)
        final = await graph.ainvoke(initial_state())

        assert fairness.calls == 0
        assert executor.calls == 0
        assert final["status"] == STATUS_FAILED
        assert final["error"]["node"] == "arbitrator"

    @pytest.mark.asyncio
    async def test_collector_failure_is_safe(self):
        collector = StubCollector(raise_error=True)
        classifier = StubClassifier()
        executor = StubExecutor()
        graph = build_graph(collector=collector, classifier=classifier, executor=executor)
        final = await graph.ainvoke(initial_state())

        assert classifier.calls == 0
        assert executor.calls == 0
        assert final["status"] == STATUS_FAILED
        assert final["error"]["node"] == "collector"

    @pytest.mark.asyncio
    async def test_classifier_node_propagates_type_onto_context(self):
        graph = build_graph()
        final = await graph.ainvoke(initial_state())

        assert final["context"].type == DisputeType.ROUTE_DEVIATION

    @pytest.mark.asyncio
    async def test_fairness_receives_expected_input_contract(self):
        fairness = StubFairness()
        graph = build_graph(fairness=fairness)
        await graph.ainvoke(initial_state())

        payload = fairness.last_input
        assert payload.dispute_id == "DRP-RYDE-001"
        assert payload.decision.verdict == Verdict.PARTIALLY_UPHELD
        assert isinstance(payload.passenger_analysis, dict)
        assert isinstance(payload.driver_analysis, dict)
        assert isinstance(payload.policy_evaluation, dict)
        assert len(payload.debate_history) == 3
        assert payload.context["dispute_id"] == "DRP-RYDE-001"


# ---------------------------------------------------------------------------
# Orchestrator legacy API compatibility
# ---------------------------------------------------------------------------


class TestOrchestratorApi:
    @pytest.mark.asyncio
    async def test_resolved_response_shape_is_legacy_compatible(self):
        orchestrator = Orchestrator(workflow=build_graph())
        response = await orchestrator.resolve(
            report_text="Driver took a longer route and overcharged me.",
            order_id="RYDE-001",
        )

        assert response["status"] == "resolved"
        assert response["dispute_id"] == "DRP-RYDE-001"
        assert response["order_id"] == "RYDE-001"
        # Legacy keys must all still be present.
        for key in (
            "dispute_id",
            "order_id",
            "status",
            "classification",
            "verdict",
            "execution",
            "debate_rounds",
            "platform_data_summary",
        ):
            assert key in response, f"missing legacy key: {key}"
        # New additive audit key.
        assert response["fairness"]["recommendation"] == "proceed"
        assert response["verdict"]["verdict"] == "partially_upheld"
        assert response["execution"]["executed"] is True
        assert response["debate_rounds"] == 3
        summary = response["platform_data_summary"]
        assert summary["trip_distance_km"] == 10.4
        assert summary["fare_discrepancy"] == 3.7
        assert summary["rider_rating"] == 4.9

    @pytest.mark.asyncio
    async def test_executor_failure_response_keeps_audit_trail(self):
        executor = StubExecutor(result={
            "executed": False,
            "status": "failed",
            "error": "refund simulation failed",
        })
        orchestrator = Orchestrator(workflow=build_graph(executor=executor))

        response = await orchestrator.resolve(
            report_text="Driver overcharged me.",
            order_id="RYDE-001",
        )

        assert response["status"] == "failed"
        assert response["error"]["node"] == "executor"
        assert response["execution"]["executed"] is False
        assert response["verdict"]["verdict"] == "partially_upheld"
        assert response["fairness"]["recommendation"] == "proceed"

    @pytest.mark.asyncio
    async def test_classifier_escalation_response_shape_is_legacy_compatible(self):
        classifier = StubClassifier(
            classification=make_classification(requires_human=True, urgency=UrgencyLevel.P0)
        )
        orchestrator = Orchestrator(workflow=build_graph(classifier=classifier))
        response = await orchestrator.resolve(
            report_text="The driver assaulted me.",
            order_id="RYDE-002",
        )

        assert response["status"] == "escalated_to_human"
        assert response["reason"] == "Safety/legal issue requires human review"
        assert response["dispute_id"] == "DRP-RYDE-001"
        assert response["classification"]["requires_human"] is True
        # Legacy platform_data payload preserved.
        platform_data = response["platform_data"]
        assert platform_data["trip"]["actual_distance_km"] == 10.4
        assert platform_data["rider_profile"] == {"rating": 4.9}
        assert platform_data["evidence"] == []

    @pytest.mark.asyncio
    async def test_fairness_escalation_response_exposes_audit_trail(self):
        fairness = StubFairness(
            assessment=make_fairness(
                recommendation=FairnessRecommendation.BLOCK,
                requires_human_review=True,
                fairness_passed=False,
                reason="Decision blocked: unverifiable references.",
            )
        )
        executor = StubExecutor()
        orchestrator = Orchestrator(
            workflow=build_graph(fairness=fairness, executor=executor)
        )
        response = await orchestrator.resolve(
            report_text="Driver overcharged me.",
            order_id="RYDE-003",
        )

        assert executor.calls == 0
        assert response["status"] == "escalated_to_human"
        assert response["reason"] == "Decision blocked: unverifiable references."
        # Requirement: expose classification, decision, fairness, execution
        # status and human-review reason on the escalation path.
        assert response["classification"]["requires_human"] is False
        assert response["verdict"]["verdict"] == "partially_upheld"
        assert response["fairness"]["recommendation"] == "block"
        assert response["fairness"]["requires_human_review"] is True
        assert response["execution"] is None

    @pytest.mark.asyncio
    async def test_node_failure_response_is_safe(self):
        arbitrator = StubArbitrator(raise_error=True)
        orchestrator = Orchestrator(workflow=build_graph(arbitrator=arbitrator))
        response = await orchestrator.resolve(
            report_text="Driver overcharged me.",
            order_id="RYDE-004",
        )

        assert response["status"] == "failed"
        assert response["error"]["node"] == "arbitrator"
        assert response["reason"] is not None
        assert response["dispute_id"] == "DRP-RYDE-001"
        assert response["classification"]["dispute_type"] == "route_deviation"
