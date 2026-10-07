"""
Agent 8: Fairness Agent

Sits between the Arbitrator and the Executor:

    Classifier -> Debate -> Arbitrator -> Fairness Agent -> Executor / Human Review

Its job is to assess whether the Arbitrator's decision was produced fairly,
based ONLY on:

    - evidence  (who was considered, and to what depth)
    - policy support  (every cited reference actually exists in retrieval)
    - reasoning consistency  (decision / rationale / compliance all agree)
    - procedural symmetry  (passenger vs driver treatment is comparable)
    - confidence  (low-confidence decisions must surface for review)

This agent must NEVER use protected or demographic characteristics to decide
fairness. ``DisputeContext.rider_profile`` / ``driver_profile`` /
``ratings`` are background context only and are intentionally ignored.

It is a hybrid agent:

    1. Deterministic checks always run (zero LLM cost).
    2. A semantic LLM review is added ONLY when deterministic checks leave
       room for genuine ambiguity, and ONLY when an LLM client is available.
    3. If the deterministic pass already requires human review, the LLM call
       is skipped — fail-safe over completeness.

The module is deliberately framework-free apart from Pydantic + the
existing ``LLMClient``, so it can later be wrapped as a LangGraph node
without code rewrites.
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field

from src.config import (
    CONFIDENCE_THRESHOLD_LOW as FAIRNESS_DECISION_CONFIDENCE_LOW,
    LLM_API_KEY,
)
from src.agents.fraud import fraud_refs
from src.core.llm_client import LLMClient
from src.core.policy_refs import case_policy_refs
from src.models.dispute_state import FairnessAssessmentInput

logger = logging.getLogger(__name__)


# ======================================================================
# Public enums and Pydantic models
# ======================================================================


class FairnessRecommendation(str, Enum):
    """Action recommendation emitted alongside the binary pass/fail flag."""

    PROCEED = "proceed"                # execute the decision as-is
    ESCALATE = "escalate"              # route to human review
    AMEND_RECOMMENDED = "amend_recommended"  # proceed with a fairness-driven amendment
    BLOCK = "block"                    # halt; do NOT execute


class FairnessIssueCode(str, Enum):
    """Discrete codes for every check the agent performs."""

    # #1 both sides considered
    ASYMMETRIC_EVIDENCE = "asymmetric_evidence"
    ONE_SIDE_NOT_CONSIDERED = "one_side_not_considered"

    # #2 decision supported by retrieved policy
    UNCITED_POLICY_REFS = "uncited_policy_refs"
    HALLUCINATED_POLICY_REFS = "hallucinated_policy_refs"
    NO_POLICY_SUPPORT = "no_policy_support"

    # #3 asymmetry / #4 reasoning
    LARGE_CONFIDENCE_GAP = "large_confidence_gap"
    UNSUPPORTED_REASONING = "unsupported_reasoning"
    INTERNAL_INCONSISTENCY = "internal_inconsistency"

    # #5 low-confidence
    LOW_DECISION_CONFIDENCE = "low_decision_confidence"

    # #6 the deciding fact cannot be verified from platform data
    DECISIVE_EVIDENCE_GAP = "decisive_evidence_gap"

    # #7 the ruling keeps a fee whose basis the platform data contradicts or does not meet
    FEE_BASIS_NOT_MET = "fee_basis_not_met"
    REFUND_BEYOND_DISPUTED = "refund_beyond_disputed_amount"

    # #8 the Fraud agent found hard evidence of fraud or collusion in this case
    FRAUD_RISK_HIGH = "fraud_risk_high"


# Verdict labels are about the COMPLAINT, not about any fee. Without this the semantic check read
# "upheld" + refund as "the fee was upheld" and flagged a correct refund as contradicting policy
# (eval run 20261001-114026, NS-001)
_VERDICT_MEANING = {
    "upheld": "the complaint is accepted: whoever filed it gets what they asked for, e.g. the fee is refunded",
    "partially_upheld": "the complaint is partly accepted: the filer gets part of what they asked for",
    "dismissed": "the complaint is rejected: the filer gets nothing, e.g. the fee stands",
}

# Dispute types whose ruling depends on where the driver was (at pickup, on the route)
_LOCATION_DECIDED_TYPES = {"no_show", "no_show_charge", "cancellation_refund", "route_deviation"}


def _advocate_ran(analysis: dict) -> bool:
    """True when an advocate produced an analysis (a stance or reasoning), even if it
    found no evidence for its side. False for a missing or failed advocate."""
    return bool(str(analysis.get("reasoning") or "").strip() or str(analysis.get("stance") or "").strip())


def _arrival_recorded(context: dict) -> bool:
    """True when the platform says the driver reached the pickup (trip field or app event)."""
    if (context.get("trip") or {}).get("driver_arrival_time"):
        return True
    return any(isinstance(e, dict) and e.get("event_type") == "driver_arrived"
               for e in context.get("app_events") or [])


def _fee_basis_problems(context: dict, verdict: str, refund) -> list[str]:
    """Deterministic checks for a ruling that leaves a no-show / cancellation fee in place.

    Prompt rules did not stop the Judge from (a) treating a driver arrival contradicted by GPS
    as proven (NS-002-C1) or (b) using the free wait instead of the no-show threshold
    (NS-002-B1), run 20261001-114026. These checks do not decide the case: they send it to a
    person when the fee's basis is contradicted or not met by the case's own data (D15)."""
    from src.agents.case_brief import _finding_values, disputed_charge
    dispute_type = getattr(context.get("type"), "value", context.get("type"))
    if dispute_type not in ("no_show", "no_show_charge", "cancellation_refund"):
        return []
    fee = disputed_charge(context)
    try:
        refunded = float(refund or 0)
    except (TypeError, ValueError):
        refunded = 0.0
    fee_kept = bool(fee) and (verdict == "dismissed" or refunded < fee - 0.01)
    if not fee_kept:
        return []
    problems = []
    conflicts = [f for f in (_dump_findings(context)) if f.get("kind") == "conflict" and "arrival" in f.get("id", "")]
    if conflicts:
        problems.append("The ruling keeps a S$%.2f fee that depends on the driver's arrival, but the platform "
                        "data contradicts that arrival: %s" % (fee, " ".join(c.get("statement", "") for c in conflicts)))
    waited = (_finding_values(context, "wait_time.waited_before_cancel") or {}).get("minutes_waited")
    threshold = (context.get("platform_policy") or {}).get("no_show_threshold_min")
    reason = str((context.get("trip") or {}).get("cancellation_reason") or "").lower()
    if waited is not None and threshold is not None and "no_show" in reason:
        try:
            if float(waited) < float(threshold):
                problems.append("The ruling keeps a no-show fee, but the driver waited %.1f min, below this "
                                "trip's no_show_threshold_min of %s." % (float(waited), threshold))
        except (TypeError, ValueError):
            pass
    # The trip's own policy waives the fee when the driver is late beyond a limit; the Judge kept
    # it although the data shows that limit passed (CR-001, run 20261002-211912)
    delay_limit = (context.get("platform_policy") or {}).get("no_fee_if_driver_delayed_beyond_eta_min")
    late = ((_finding_values(context, "wait_time.no_arrival") or {}).get("minutes_after_scheduled")
            if _finding_values(context, "wait_time.no_arrival")
            else (_finding_values(context, "wait_time.arrival_vs_scheduled") or {}).get("minutes_late"))
    if delay_limit is not None and late is not None:
        try:
            if float(late) > float(delay_limit):
                problems.append("The ruling keeps the fee, but the driver was %.1f min past the scheduled "
                                "pickup / ETA, beyond this trip's no_fee_if_driver_delayed_beyond_eta_min of "
                                "%s." % (float(late), delay_limit))
        except (TypeError, ValueError):
            pass
    return problems


def _refund_basis_problems(context: dict, refund) -> list[str]:
    """A refund larger than the amount in dispute that the platform data computes (the fee charged,
    or the excess over the quoted fare) has no rule the system can check behind the extra money.
    The Judge refunded a whole S$22.60 fare where only the S$4.20 detour excess was refundable
    (SQ-002, run 20261002-211912). Not decided here: the case goes to a person (D17)."""
    from src.agents.case_brief import disputed_charge
    disputed = disputed_charge(context)
    try:
        refunded = float(refund or 0)
    except (TypeError, ValueError):
        return []
    if disputed and refunded > disputed + 0.01:
        return ["The refund S$%.2f is larger than the S$%.2f in dispute that the platform data computes; "
                "no checkable rule covers the difference." % (refunded, disputed)]
    # Service-quality complaints (rude or unsafe driving) have no refund schedule in Ryde's policy:
    # compensation is at Ryde's discretion, so any amount beyond a fare overcharge is a person's call,
    # not the model's (user decision 2026-10-04; SQ-001 auto-refunded a whole S$27.40 fare).
    # Cleaning fees and driver claims are not covered here: their amounts come from fee and cap rules.
    dispute_type = getattr(context.get("type"), "value", context.get("type"))
    if dispute_type == "service_quality" and refunded > 0 and not disputed:
        return ["The refund S$%.2f in a service-quality dispute rests on Ryde's discretion: no policy rule "
                "sets an amount, so a person decides it." % refunded]
    return []


def _dump_findings(context: dict) -> list[dict]:
    return [f if isinstance(f, dict) else f.model_dump() for f in context.get("findings") or []]


def _fare_is_metered(context: dict) -> bool:
    """True when the platform data says the fare was metered (it grows with the route
    driven), not fixed upfront. A metered fare can only be checked against the route."""
    basis = str((context.get("platform_policy") or {}).get("fare_basis") or "").lower()
    if basis.startswith("metered"):
        return True
    return any(isinstance(e, dict) and e.get("event_type") == "booking_confirmed"
               and "metered fare" in str(e.get("details") or "").lower()
               for e in context.get("app_events") or [])


def _location_evidence_gaps(context: dict) -> list[str]:
    """Collector gaps that leave the driver's location unverifiable, for dispute
    types where that location decides the case. Empty list = nothing blocking."""
    dispute_type = getattr(context.get("type"), "value", context.get("type"))
    # A metered fare is decided by the route driven, so a GPS gap blocks it like a route
    # deviation; an upfront fare is fixed by the quote and is not (eval case FD-003)
    location_decided = dispute_type in _LOCATION_DECIDED_TYPES or (
        dispute_type == "fare_dispute" and _fare_is_metered(context))
    if not location_decided:
        return []
    # A cancellation where the platform records no driver arrival is decided by timing
    # (free window after match), not by where the driver was (eval case CR-002-M2)
    if dispute_type == "cancellation_refund" and not _arrival_recorded(context):
        return []
    gaps = []
    for f in context.get("findings") or []:
        if not isinstance(f, dict) or f.get("kind") != "gap":
            continue
        fid = f.get("id", "")
        missing = (f.get("value") or {}).get("missing") or []
        if fid == "data_gaps.gps_signal_lost" or (
                fid == "data_gaps.missing_sources" and any("gps" in m for m in missing)):
            gaps.append(f.get("statement", fid))
    return gaps


class FairnessIssueDetail(BaseModel):
    """A single auditable finding."""

    code: FairnessIssueCode
    severity: str = "low"               # "low" | "medium" | "high"
    description: str
    evidence_refs: list[str] = []
    recommended_action: str = ""


class FairnessAuditDetail(BaseModel):
    """Structured, machine-readable audit trail."""

    evidence_counts: dict
    confidence_gap: float | None
    passenger_confidence: float | None
    driver_confidence: float | None
    decision_confidence: float
    policies_cited_in_decision: list[str]
    policies_retrieved: list[str]
    policies_uncited: list[str]
    hallucinated_policy_refs: list[str]
    policy_compliance_alignment: str | None   # aligned | partial | misaligned | unknown
    rationale_length_chars: int
    rationale_cites_evidence: bool
    passenger_passenger_compliant: Any | None
    driver_passenger_compliant: Any | None
    verdict: str
    semantic_review_used: bool
    semantic_review_skipped_reason: str | None = None


class FairnessAssessment(BaseModel):
    """Top-level result returned by ``FairnessAgent.assess``."""

    fairness_passed: bool
    confidence: float = Field(ge=0.0, le=1.0)  # confidence in the *assessment*
    issues: list[FairnessIssueDetail] = []
    recommendation: FairnessRecommendation
    requires_human_review: bool
    audit_details: FairnessAuditDetail
    assessed_at: str                           # ISO-8601
    reason: str                                # short top-line summary


# ======================================================================
# Default thresholds (mirrored from src/config; only used if absent there)
# ======================================================================

_DEFAULT_FAIRNESS_CONFIDENCE_GAP = 0.30   # |passenger_conf - driver_conf| > 0.3
_DEFAULT_RATIONALE_MIN_LENGTH = 20        # characters
_DEFAULT_EVIDENCE_COUNT_GAP = 3           # passenger vs driver evidence length gap
# Semantic-review prompt budget: Groq's free tier allows 8k tokens a minute, so the
# whole prompt stays around 4k tokens (~16k characters)
_ANALYSIS_MAX_CHARS = 2000                # per advocate / policy analysis
_EVIDENCE_LIST_MAX_ITEMS = 25             # app events, chat lines, findings each
_EVIDENCE_LINE_MAX_CHARS = 180


# ======================================================================
# Helpers
# ======================================================================


def _clamp_unit(value, default: float = 0.0) -> float:
    """Best-effort float clamp to [0.0, 1.0]; safe against None/strings."""
    try:
        v = float(value)
    except (TypeError, ValueError):
        return default
    return max(0.0, min(1.0, v))


def _safe_dict_list(value, key: str) -> list:
    """Return ``value[key]`` if it is a list, otherwise an empty list."""
    if not isinstance(value, dict):
        return []
    items = value.get(key)
    return items if isinstance(items, list) else []


def _rectify_severity(severity: str) -> str:
    """Clamp severity to the allowed vocabulary."""
    return severity if severity in ("low", "medium", "high") else "low"


# ======================================================================
# Fairness Agent
# ======================================================================


class FairnessAgent:
    """
    Hybrid (deterministic + semantic) fairness assessor.

    Deterministic checks ALWAYS run. A semantic LLM review is added only when
    the deterministic pass leaves genuine ambiguity and an LLM client is
    available. If the deterministic pass already requires human review, the
    LLM call is skipped.
    """

    def __init__(self, llm_client: LLMClient | None = None):
        self.name = "Fairness"
        self._llm_client = llm_client

    # ------------------------------------------------------------------
    # LLM client lazy accessor
    # ------------------------------------------------------------------

    def _get_llm_client(self) -> LLMClient | None:
        if self._llm_client is not None:
            return self._llm_client
        if not LLM_API_KEY:
            return None
        try:
            self._llm_client = LLMClient()
        except Exception as exc:
            logger.warning("Could not initialise LLMClient: %s", exc)
            self._llm_client = None
        return self._llm_client

    # ------------------------------------------------------------------
    # Public entry point
    # ------------------------------------------------------------------

    async def assess(self, input_payload: FairnessAssessmentInput) -> FairnessAssessment:
        """
        Run deterministic checks, optionally augment with a semantic review,
        and return a structured :class:`FairnessAssessment`.

        Never raises — returns a safe, auditable result on any failure.
        """

        assessed_at = datetime.now(timezone.utc).isoformat()

        # Safe fallback: malformed / missing inputs.
        try:
            decision = input_payload.decision
            passenger_analysis = input_payload.passenger_analysis or {}
            driver_analysis = input_payload.driver_analysis or {}
            policy_evaluation = input_payload.policy_evaluation or {}
            debate_history = input_payload.debate_history or []
            context = input_payload.context or {}
        except Exception as exc:
            logger.warning("FairnessAgent input payload invalid: %s", exc)
            return self._safe_assessment(
                "fairness_assessment_unavailable",
                reason=f"Invalid fairness input payload: {exc}",
                assessed_at=assessed_at,
            )

        try:
            return await self._assess(
                dispute_id=input_payload.dispute_id,
                decision=decision,
                passenger_analysis=passenger_analysis,
                driver_analysis=driver_analysis,
                policy_evaluation=policy_evaluation,
                debate_history=debate_history,
                context=context,
                assessed_at=assessed_at,
            )
        except Exception as exc:
            logger.exception("FairnessAgent.assess crashed safely: %s", exc)
            return self._safe_assessment(
                "fairness_assessment_error",
                reason=f"Fairness assessment failed safely: {type(exc).__name__}: {exc}",
                assessed_at=assessed_at,
            )

    # ------------------------------------------------------------------
    # Core assessment logic
    # ------------------------------------------------------------------

    async def _assess(
        self,
        dispute_id: str,
        decision,
        passenger_analysis: dict,
        driver_analysis: dict,
        policy_evaluation: dict,
        debate_history: list[dict],
        context: dict,
        assessed_at: str,
    ) -> FairnessAssessment:
        # ---- 1. Pull numbers and refs ----------------------------------
        passenger_conf = _clamp_unit(passenger_analysis.get("confidence"))
        driver_conf = _clamp_unit(driver_analysis.get("confidence"))
        decision_conf = _clamp_unit(getattr(decision, "confidence", 0.0))

        passenger_evidence = _safe_dict_list(passenger_analysis, "evidence")
        driver_evidence = _safe_dict_list(driver_analysis, "evidence")
        passenger_count = len(passenger_evidence)
        driver_count = len(driver_evidence)

        cited_refs: list[str] = list(getattr(decision, "policy_references", []) or [])
        retrieved_refs = self._build_valid_refs(policy_evaluation, context)
        # Fraud signals are a real source the Judge saw (design guard 1: accepted from day one),
        # but not policy clauses, so they do not count toward the "uncited clauses" heuristic
        hallucinated_refs = sorted({r for r in cited_refs if r not in retrieved_refs | fraud_refs(context)})
        uncited_retrieved = sorted(retrieved_refs - set(cited_refs))

        rationale = (getattr(decision, "rationale", "") or "").strip()
        verdict_value = getattr(getattr(decision, "verdict", None), "value", None)
        if verdict_value is None:
            verdict_value = str(getattr(decision, "verdict", "unknown"))

        # ---- 2. Deterministic checks ----------------------------------
        issues: list[FairnessIssueDetail] = []
        requires_human: bool = False

        def add_issue(
            code: FairnessIssueCode,
            description: str,
            severity: str = "medium",
            refs: list[str] | None = None,
            recommended_action: str = "",
        ) -> None:
            issues.append(FairnessIssueDetail(
                code=code,
                severity=_rectify_severity(severity),
                description=description,
                evidence_refs=list(refs or []),
                recommended_action=recommended_action,
            ))

        # (a) one side not considered. A side counts as considered when its advocate
        #     produced an analysis. An advocate that analysed the case and found
        #     nothing in its side's favour (e.g. GPS proves the driver waited) is a
        #     finding against that side, not a side that was ignored.
        passenger_heard = passenger_count > 0 or _advocate_ran(passenger_analysis)
        driver_heard = driver_count > 0 or _advocate_ran(driver_analysis)
        if (not passenger_heard and not driver_heard) or (passenger_count == 0 and driver_count == 0):
            add_issue(
                FairnessIssueCode.ONE_SIDE_NOT_CONSIDERED,
                "Neither side's position is backed by any evidence item, so the ruling has nothing to rest on.",
                severity="high",
                recommended_action="Escalate to a human reviewer before executing.",
            )
            requires_human = True
        elif not passenger_heard or not driver_heard:
            missing = "passenger" if not passenger_heard else "driver"
            add_issue(
                FairnessIssueCode.ONE_SIDE_NOT_CONSIDERED,
                f"The {missing}'s position was not analysed at all.",
                severity="high",
                recommended_action="Escalate to a human reviewer before executing.",
            )
            requires_human = True
        elif passenger_count == 0 or driver_count == 0:
            # Medium: recorded and sent to the semantic review, which checks the
            # ruling is grounded; it does not block execution by itself
            empty = "passenger" if passenger_count == 0 else "driver"
            add_issue(
                FairnessIssueCode.ASYMMETRIC_EVIDENCE,
                f"The {empty}'s advocate analysed the case but found no evidence supporting the {empty}.",
                severity="medium",
                recommended_action="Confirm the ruling rests on the case evidence, not on the absence of a rebuttal.",
            )
        else:
            # (b) asymmetric evidence (only counts as asymmetry when both sides present)
            # Low: one side often simply has more evidence; this is a note, not a verdict flaw
            gap = abs(passenger_count - driver_count)
            if gap >= _DEFAULT_EVIDENCE_COUNT_GAP:
                heavier = "passenger" if passenger_count > driver_count else "driver"
                add_issue(
                    FairnessIssueCode.ASYMMETRIC_EVIDENCE,
                    (
                        f"Evidence is asymmetric: passenger provided {passenger_count} "
                        f"item(s), driver provided {driver_count} item(s) "
                        f"(gap={gap})."
                    ),
                    severity="low",
                    recommended_action="Confirm the lighter side received a fair chance to respond.",
                )

        # (c) large confidence imbalance -- low: advocates diverge whenever the
        # evidence clearly favours one side, which is expected rather than unfair
        confidence_gap = abs(passenger_conf - driver_conf)
        if passenger_count > 0 and driver_count > 0 and confidence_gap > _DEFAULT_FAIRNESS_CONFIDENCE_GAP:
            add_issue(
                FairnessIssueCode.LARGE_CONFIDENCE_GAP,
                (
                    f"Large unexplained confidence imbalance between sides: "
                    f"passenger={passenger_conf:.2f}, driver={driver_conf:.2f} "
                    f"(gap={confidence_gap:.2f})."
                ),
                severity="low",
                recommended_action="Verify the imbalance is justified by evidence weight.",
            )

        # (d) missing / uncited policy support
        if retrieved_refs and not cited_refs:
            add_issue(
                FairnessIssueCode.NO_POLICY_SUPPORT,
                (
                    "Decision did not cite any policy clause, but policy "
                    "clauses were retrieved for evaluation."
                ),
                severity="high",
                refs=sorted(retrieved_refs),
                recommended_action="Escalate so an arbitrator can attach policy grounding.",
            )
            requires_human = True
        elif not retrieved_refs and cited_refs:
            # Decision cites policies we cannot verify — treat as concerning.
            add_issue(
                FairnessIssueCode.NO_POLICY_SUPPORT,
                (
                    "Decision cites policy references, but no policy clauses "
                    "were available to verify them."
                ),
                severity="high",
                refs=cited_refs,
                recommended_action="Escalate; do not execute without policy grounding.",
            )
            requires_human = True
        elif retrieved_refs and cited_refs and len(cited_refs) < max(1, len(retrieved_refs) // 2):
            # Heuristic: only cited a small fraction of retrieved clauses.
            add_issue(
                FairnessIssueCode.UNCITED_POLICY_REFS,
                (
                    f"Decision cites only {len(cited_refs)} of "
                    f"{len(retrieved_refs)} retrieved clauses. Several "
                    f"relevant clauses were not addressed."
                ),
                severity="low",
                refs=uncited_retrieved[:10],
            )

        # (e) hallucinated policy refs (cited but not retrieved)
        if hallucinated_refs:
            add_issue(
                FairnessIssueCode.HALLUCINATED_POLICY_REFS,
                (
                    f"Decision cites {len(hallucinated_refs)} policy reference(s) "
                    "not present in the retrieved clauses — these are "
                    "unverifiable and must not influence execution."
                ),
                severity="high",
                refs=hallucinated_refs,
                recommended_action="Re-run arbitration with grounded references, then re-assess.",
            )
            requires_human = True

        # (f) internal inconsistencies: decision verdict vs policy compliance
        pc_field = policy_evaluation.get("passenger_compliant") if isinstance(policy_evaluation, dict) else None
        dc_field = policy_evaluation.get("driver_compliant") if isinstance(policy_evaluation, dict) else None
        if pc_field is not None and dc_field is not None:
            # The verdict is about the complaint, so read compliance from the
            # complainant's side: a driver-filed dispute that is UPHELD favours the driver.
            filer = "driver" if str((context or {}).get("reporter", "")).lower() == "driver" else "passenger"
            other = "passenger" if filer == "driver" else "driver"
            filer_ok, other_ok = (dc_field, pc_field) if filer == "driver" else (pc_field, dc_field)
            contradictions: list[str] = []
            if verdict_value == "upheld" and filer_ok is False and other_ok is True:
                contradictions.append(
                    f"The policy check marks the {filer} (who filed) non-compliant and the {other} "
                    "compliant, yet the verdict UPHOLDS the complaint."
                )
            if verdict_value == "dismissed" and filer_ok is True and other_ok is False:
                contradictions.append(
                    f"The policy check marks the {other} non-compliant and the {filer} (who filed) "
                    "compliant, yet the verdict DISMISSES the complaint."
                )
            # Medium: this is the Policy agent disagreeing with the Judge, not the Judge
            # contradicting itself; the semantic review weighs it against the evidence.
            for text in contradictions:
                add_issue(
                    FairnessIssueCode.INTERNAL_INCONSISTENCY,
                    text,
                    severity="medium",
                    recommended_action="Check that the rationale explains why it departs from the policy check.",
                )

        # Also flag inconsistencies between rationale and evidence only if the
        # rationale is suspiciously short relative to the dispute complexity.
        if rationale and len(rationale) < _DEFAULT_RATIONALE_MIN_LENGTH:
            add_issue(
                FairnessIssueCode.UNSUPPORTED_REASONING,
                "Rationale is too short to be supported by the considered evidence.",
                severity="medium",
                recommended_action="Require a more detailed rationale before proceeding.",
            )

        # (g) low arbitrator decision confidence
        if decision_conf <= FAIRNESS_DECISION_CONFIDENCE_LOW:
            add_issue(
                FairnessIssueCode.LOW_DECISION_CONFIDENCE,
                (
                    f"Arbitrator confidence ({decision_conf:.2f}) is at or below "
                    f"the fairness-low threshold "
                    f"({FAIRNESS_DECISION_CONFIDENCE_LOW:.2f})."
                ),
                severity="high",
                recommended_action="Route to human review before any execution.",
            )
            requires_human = True

        # (h) the fact the ruling turns on cannot be checked: in these disputes it
        #     is where the driver was, so lost or missing driver GPS leaves only the
        #     two parties' word against each other. No confidence score can fix that.
        gps_gaps = _location_evidence_gaps(context)
        if gps_gaps:
            add_issue(
                FairnessIssueCode.DECISIVE_EVIDENCE_GAP,
                "Where the driver was is what decides this dispute, but it cannot be "
                "verified: " + " ".join(gps_gaps),
                severity="high",
                refs=["collector.findings"],
                recommended_action="Route to human review; the ruling would rest on one party's word.",
            )
            requires_human = True

        # (i) the ruling keeps a fee whose basis the case data contradicts or does not meet
        for problem in _fee_basis_problems(context or {}, verdict_value,
                                           getattr(decision, "refund_amount", None)):
            add_issue(
                FairnessIssueCode.FEE_BASIS_NOT_MET,
                problem,
                severity="high",
                refs=["collector.findings", "platform_policy"],
                recommended_action="Route to human review; the fee rests on a record the data does not support.",
            )
            requires_human = True

        # (j) the refund goes beyond the disputed amount the platform data computes
        for problem in _refund_basis_problems(context or {}, getattr(decision, "refund_amount", None)):
            add_issue(
                FairnessIssueCode.REFUND_BEYOND_DISPUTED,
                problem,
                severity="high",
                refs=["collector.findings", "platform_policy"],
                recommended_action="Route to human review; the extra amount has no rule the system can verify.",
            )
            requires_human = True

        # (k) hard evidence of fraud or collusion: a person decides, with the Judge's draft and
        #     the report. Priors alone never reach HIGH, so this never fires on history only.
        fraud = (context or {}).get("fraud_report") or {}
        if fraud.get("level") == "high":
            hard = [s for s in fraud.get("signals") or [] if s.get("kind") == "hard"]
            add_issue(
                FairnessIssueCode.FRAUD_RISK_HIGH,
                "Fraud agent: " + " ".join(s.get("statement", "") for s in hard),
                severity="high",
                refs=[f"fraud_report.{s.get('code')}" for s in hard],
                recommended_action="Route to human review with the fraud report; do not auto-dismiss the claim.",
            )
            requires_human = True

        # ---- 3. Decide on LLM semantic review ----------------------
        semantic_review_used = False
        semantic_skipped_reason: str | None = None

        high_severity_present = any(i.severity == "high" for i in issues)
        medium_severity_present = any(i.severity == "medium" for i in issues)
        skipped_due_to_escalation = requires_human or high_severity_present

        if skipped_due_to_escalation or not self._should_call_semantic(
            issues, decision_conf, cites=bool(cited_refs), has_evidence=passenger_count > 0 and driver_count > 0
        ):
            semantic_skipped_reason = (
                "deterministic findings already require human review"
                if (requires_human or high_severity_present)
                else "deterministic checks already decisive"
            )
        else:
            llm = self._get_llm_client()
            if llm is None:
                semantic_skipped_reason = "no LLM client available"
            else:
                semantic_issues = await self._call_semantic_review(
                    llm,
                    dispute_id=dispute_id,
                    decision=decision,
                    passenger_analysis=passenger_analysis,
                    driver_analysis=driver_analysis,
                    policy_evaluation=policy_evaluation,
                    context=context,
                    rationale=rationale,
                    verdict_value=verdict_value,
                    issues_so_far=issues,
                )
                if semantic_issues is not None:
                    issues.extend(semantic_issues)
                    semantic_review_used = True
                else:
                    semantic_skipped_reason = "semantic review returned no usable JSON"

        # ---- 4. Build audit details ---------------------------------
        rationale_cites_evidence = self._rationale_cites_evidence(
            rationale, passenger_evidence, driver_evidence, context
        )
        alignment = self._alignment_label(
            verdict_value, pc_field, dc_field, decision_conf, requires_human
        )

        audit = FairnessAuditDetail(
            evidence_counts={
                "passenger": passenger_count,
                "driver": driver_count,
            },
            confidence_gap=round(confidence_gap, 4),
            passenger_confidence=round(passenger_conf, 4),
            driver_confidence=round(driver_conf, 4),
            decision_confidence=round(decision_conf, 4),
            policies_cited_in_decision=sorted(set(cited_refs)),
            policies_retrieved=sorted(retrieved_refs),
            policies_uncited=uncited_retrieved,
            hallucinated_policy_refs=hallucinated_refs,
            policy_compliance_alignment=alignment,
            rationale_length_chars=len(rationale),
            rationale_cites_evidence=rationale_cites_evidence,
            passenger_passenger_compliant=pc_field,
            driver_passenger_compliant=dc_field,
            verdict=verdict_value,
            semantic_review_used=semantic_review_used,
            semantic_review_skipped_reason=semantic_skipped_reason,
        )

        # ---- 5. Compose recommendation and final assessment ----------
        recommendation, fairness_passed = self._compose_recommendation(
            issues=issues,
            decision_conf=decision_conf,
            semantic_used=semantic_review_used,
        )

        # If deterministic findings already say human-review is needed,
        # ensure the final flag sticks even if recommendation says PROCEED.
        final_requires_human = requires_human or recommendation in (
            FairnessRecommendation.ESCALATE,
            FairnessRecommendation.BLOCK,
        )

        # Confidence in the assessment = 1 - weighted_issue_penalty, bounded.
        assessment_confidence = self._assessment_confidence(
            issues=issues,
            semantic_used=semantic_review_used,
            decision_conf=decision_conf,
        )

        reason = self._reason_string(
            fairness_passed=fairness_passed,
            recommendation=recommendation,
            issues=issues,
        )

        return FairnessAssessment(
            fairness_passed=fairness_passed,
            confidence=assessment_confidence,
            issues=issues,
            recommendation=recommendation,
            requires_human_review=final_requires_human,
            audit_details=audit,
            assessed_at=assessed_at,
            reason=reason,
        )

    # ------------------------------------------------------------------
    # LLM semantic review (best-effort, never raises)
    # ------------------------------------------------------------------

    def _should_call_semantic(
        self,
        issues: list[FairnessIssueDetail],
        decision_conf: float,
        cites: bool,
        has_evidence: bool,
    ) -> bool:
        # Only useful when there IS something to scrutinise and the agent is
        # not already in "block / escalate" territory.
        if not has_evidence:
            return False
        if decision_conf <= FAIRNESS_DECISION_CONFIDENCE_LOW:
            return False
        if not cites:
            # No policy support is itself a high-severity deterministic issue;
            # the semantic layer won't add value here.
            return False
        # Skip if deterministic findings are decisive (severe).
        severe = [i for i in issues if i.severity == "high"]
        if severe:
            return False
        return True

    async def _call_semantic_review(
        self,
        llm: LLMClient,
        dispute_id: str,
        decision,
        passenger_analysis: dict,
        driver_analysis: dict,
        policy_evaluation: dict,
        context: dict,
        rationale: str,
        verdict_value: str,
        issues_so_far: list[FairnessIssueDetail],
    ) -> list[FairnessIssueDetail] | None:
        """
        Query the LLM to surface subtle fairness concerns (unsupported
        reasoning, asymmetric reasoning, rationale↔evidence alignment).

        Returns ``None`` on any failure — the caller treats that as
        "no semantic contribution".
        """

        system_prompt = self._build_semantic_system_prompt()
        case_evidence = _case_evidence_summary(context)
        user_prompt = self._build_semantic_user_prompt(
            dispute_id=dispute_id,
            decision=decision,
            passenger_analysis=passenger_analysis,
            driver_analysis=driver_analysis,
            policy_evaluation=policy_evaluation,
            rationale=rationale,
            verdict_value=verdict_value,
            issues_so_far=issues_so_far,
            case_evidence=case_evidence,
        )
        # Everything the reviewer was shown; a finding may only point at text from here
        grounding_text = "\n".join((
            case_evidence, rationale,
            json.dumps(passenger_analysis, default=str), json.dumps(driver_analysis, default=str),
            json.dumps(policy_evaluation, default=str),
        ))

        try:
            raw = await llm.chat_json(
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                temperature=0.2,
            )
        except Exception as exc:
            logger.warning("FairnessAgent semantic review LLM call failed: %s", exc)
            return None

        parsed = self._parse_llm_json(raw)
        if not parsed:
            return None

        # Validate and coerce
        try:
            return self._coerce_semantic_issues(
                parsed,
                retrieved_refs=self._build_valid_refs(policy_evaluation, context),
                grounding_text=grounding_text,
            )
        except Exception as exc:
            logger.warning("FairnessAgent semantic review JSON invalid: %s", exc)
            return None

    def _build_semantic_system_prompt(self) -> str:
        return (
            "You are the Fairness Agent in a ride-hailing dispute resolution "
            "system. You are assessing whether the Arbitrator's decision was "
            "produced fairly.\n\n"
            "Rules:\n"
            "- Base your judgment ONLY on evidence, policy support, reasoning "
            "consistency, procedural symmetry, and confidence.\n"
            "- Do NOT infer protected or demographic characteristics "
            "(race, gender, religion, nationality, age, etc.).\n"
            "- Do NOT expose chain-of-thought; return only the final "
            "findings.\n"
            "- The CASE EVIDENCE section is the ground truth. The advocate "
            "analyses are summaries: if a fact is missing from a summary, check "
            "the case evidence before calling the decision unsupported.\n"
            "- Report internal_inconsistency or unsupported_reasoning only when "
            "the decision contradicts the case evidence, the policy evaluation "
            "or itself. Use severity \"high\" only for a contradiction that would "
            "change the outcome.\n"
            "- In evidence_refs, quote the exact conflicting items: an event type "
            "with its timestamp, a chat timestamp, a short exact phrase from the "
            "rationale, or a policy reference. A high finding without such a "
            "quote is treated as medium.\n"
            "- If the case is clearly fair, return an empty issues list.\n"
            "- If you find a fairness concern, return it as one entry in the "
            "issues list.\n\n"
            "Respond ONLY with a valid JSON object (no markdown, no extra "
            "text) with exactly these keys:\n"
            '  "issues": list of objects, each with keys:\n'
            '      "code": one of: "asymmetric_evidence", '
            '"one_side_not_considered", "uncited_policy_refs", '
            '"hallucinated_policy_refs", "no_policy_support", '
            '"large_confidence_gap", "unsupported_reasoning", '
            '"internal_inconsistency", "low_decision_confidence"\n'
            '      "severity": "low" | "medium" | "high"\n'
            '      "description": string\n'
            '      "evidence_refs": list of strings (exact quotes of the '
            'conflicting evidence items or policy refs, may be empty)\n'
            '      "recommended_action": string\n'
            '  "rationale_alignment": "aligned" | "partial" | '
            '"misaligned" | "unknown"\n'
        )

    def _build_semantic_user_prompt(
        self,
        dispute_id: str,
        decision,
        passenger_analysis: dict,
        driver_analysis: dict,
        policy_evaluation: dict,
        rationale: str,
        verdict_value: str,
        issues_so_far: list[FairnessIssueDetail],
        case_evidence: str = "",
    ) -> str:
        return (
            f"Dispute ID: {dispute_id}\n"
            f"Verdict: {verdict_value} ({_VERDICT_MEANING.get(verdict_value, 'see rationale')}); "
            f"refund: {getattr(decision, 'refund_amount', None)}\n"
            f"Decision confidence: {getattr(decision, 'confidence', 0.0)}\n"
            f"Rationale: {rationale[:1200]}\n\n"
            f"Cited policy refs: {list(getattr(decision, 'policy_references', []) or [])}\n\n"
            f"CASE EVIDENCE (platform records, ground truth):\n"
            f"{case_evidence or '(not available)'}\n\n"
            f"Passenger analysis (summary): "
            f"{_truncate_dict(passenger_analysis, _ANALYSIS_MAX_CHARS)}\n\n"
            f"Driver analysis (summary): "
            f"{_truncate_dict(driver_analysis, _ANALYSIS_MAX_CHARS)}\n\n"
            f"Policy evaluation (summary): "
            f"{_truncate_dict(policy_evaluation, _ANALYSIS_MAX_CHARS)}\n\n"
            f"Deterministic findings already raised:\n"
            f"{self._format_issues_summary(issues_so_far)}\n\n"
            "Return ONLY a JSON object per the system prompt. Do not repeat "
            "the deterministic findings unless the semantic layer adds "
            "something new."
        )

    def _coerce_semantic_issues(
        self,
        parsed: dict,
        retrieved_refs: set[str],
        grounding_text: str = "",
    ) -> list[FairnessIssueDetail]:
        haystack = " ".join(grounding_text.split()).lower()

        def grounded(ref: str) -> bool:
            # A policy ref we retrieved, or a quote (>= 4 chars) of what the reviewer was shown
            quote = " ".join(ref.split()).lower().strip("\"'")
            return ref in retrieved_refs or (len(quote) >= 4 and quote in haystack)

        items = parsed.get("issues", [])
        if not isinstance(items, list):
            return []
        coerced: list[FairnessIssueDetail] = []
        for item in items:
            if not isinstance(item, dict):
                continue
            code_str = item.get("code")
            if not code_str:
                continue
            try:
                code = FairnessIssueCode(code_str)
            except ValueError:
                # Unknown code from the LLM — drop silently to stay safe.
                continue
            severity = _rectify_severity(str(item.get("severity", "low")))
            description = str(item.get("description", "")).strip() or "No description provided."
            raw_refs = item.get("evidence_refs", []) or []
            refs = [str(r) for r in raw_refs] if isinstance(raw_refs, list) else []
            # Keep only refs that point at something real, to prevent
            # prompt-injection style fabrication.
            refs = [r for r in refs if grounded(r)]
            if severity == "high" and not refs:
                # A blocking finding must show the conflicting evidence; otherwise it is a note
                severity = "medium"
                description += " (not tied to specific evidence; downgraded from high)"
            coerced.append(FairnessIssueDetail(
                code=code,
                severity=severity,
                description=description,
                evidence_refs=refs,
                recommended_action=str(item.get("recommended_action", "")).strip(),
            ))
        return coerced

    # ------------------------------------------------------------------
    # Deterministic analysis helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _build_valid_refs(policy_evaluation: dict, context: dict | None = None) -> set[str]:
        """Accept retrieved clauses and explicit platform case-policy fields."""
        refs = case_policy_refs(context)
        # Clauses in the shared Case Brief (complaint search, topics, advocates' requests) were
        # really retrieved and shown to every agent; without them a Judge citing a topic clause
        # looked hallucinated (eval run 20261001-114026, FD-002 family, D14)
        brief = (context or {}).get("case_brief") if isinstance(context, dict) else None
        refs.update(c["reference"] for c in (brief or {}).get("clauses") or [] if c.get("reference"))
        if not isinstance(policy_evaluation, dict):
            return refs
        for key in ("policies", "chunks", "clauses"):
            items = policy_evaluation.get(key, [])
            if isinstance(items, list):
                for idx, item in enumerate(items):
                    if isinstance(item, dict):
                        source = item.get("source", "unknown")
                        chunk = item.get("chunk_index", idx)
                        refs.add(f"{source}#{chunk}")
        # The Policy agent returns the references it already checked against
        # the retrieved clauses; without these every citation looks hallucinated
        for ref in policy_evaluation.get("policy_references") or []:
            if isinstance(ref, str) and ref:
                refs.add(ref)
        return refs

    @staticmethod
    def _rationale_cites_evidence(
        rationale: str,
        passenger_evidence: list,
        driver_evidence: list,
        context: dict,
    ) -> bool:
        """Cheap heuristic: does the rationale mention any verifiable
        evidence tokens (GPS, chat, payment, evidence ids, etc.)?"""
        if not rationale:
            return False
        lowered = rationale.lower()
        tokens = ["gps", "chat", "payment", "evidence", "refund", "fare",
                  "receipt", "route", "trip", "policy", "ride"]
        if any(tok in lowered for tok in tokens):
            return True
        # Numeric claim (e.g. "5.50", "67%") in the rationale, which usually
        # reflects a concrete fact derived from evidence.
        if any(ch.isdigit() for ch in rationale):
            return True
        # Fall through.
        return False

    @staticmethod
    def _alignment_label(
        verdict_value: str,
        passenger_compliant: Any,
        driver_compliant: Any,
        decision_conf: float,
        requires_human: bool,
    ) -> str | None:
        if requires_human:
            return "unknown"
        if passenger_compliant is None and driver_compliant is None:
            return "unknown"
        if passenger_compliant is None or driver_compliant is None:
            return "partial"
        # Both known:
        if verdict_value in ("upheld", "dismissed", "partially_upheld"):
            # No categorical rule that maps 1:1; surface "partial" unless
            # both sides are non-compliant (reasonable for upheld) or both
            # compliant (reasonable for dismissed), which counts as aligned.
            if passenger_compliant is False and driver_compliant is False:
                return "aligned"
            if passenger_compliant is True and driver_compliant is True:
                return "aligned"
            return "partial"
        return "unknown"

    # ------------------------------------------------------------------
    # Recommendation + confidence aggregation
    # ------------------------------------------------------------------

    @staticmethod
    def _compose_recommendation(
        issues: list[FairnessIssueDetail],
        decision_conf: float,
        semantic_used: bool,
    ) -> tuple[FairnessRecommendation, bool]:
        high = [i for i in issues if i.severity == "high"]
        medium = [i for i in issues if i.severity == "medium"]

        if any(i.code == FairnessIssueCode.HALLUCINATED_POLICY_REFS for i in high):
            # Unverifiable policy anchors cannot be allowed to influence
            # execution; that is the strongest block signal.
            return FairnessRecommendation.BLOCK, False
        # Only high-severity findings stop execution; medium ones are recorded
        # and shown to reviewers, but the decision still executes.
        if high:
            return FairnessRecommendation.ESCALATE, False
        if medium:
            return FairnessRecommendation.AMEND_RECOMMENDED, True
        # Otherwise proceed.
        return FairnessRecommendation.PROCEED, True

    @staticmethod
    def _assessment_confidence(
        issues: list[FairnessIssueDetail],
        semantic_used: bool,
        decision_conf: float,
    ) -> float:
        # Start high, decrement by finding severity, then clamp.
        conf = 0.8 if semantic_used else 0.7
        for issue in issues:
            if issue.severity == "high":
                conf -= 0.20
            elif issue.severity == "medium":
                conf -= 0.10
            else:
                conf -= 0.04
        # Align with the arbitrator's confidence, but bounded.
        try:
            blend = 0.5 * conf + 0.5 * max(0.0, decision_conf)
        except Exception:
            blend = conf
        return round(_clamp_unit(blend), 4)

    @staticmethod
    def _reason_string(
        fairness_passed: bool,
        recommendation: FairnessRecommendation,
        issues: list[FairnessIssueDetail],
    ) -> str:
        if fairness_passed and not issues:
            return "Decision appears fair and ready to execute."
        if recommendation == FairnessRecommendation.BLOCK:
            return f"Decision blocked: {len(issues)} fairness issue(s), including unverifiable references."
        if recommendation == FairnessRecommendation.ESCALATE:
            return f"Decision requires human review: {len(issues)} fairness issue(s)."
        if recommendation == FairnessRecommendation.AMEND_RECOMMENDED:
            return f"Proceed with caution: {len(issues)} fairness concern(s) to note."
        return f"{len(issues)} fairness issue(s) noted."

    @staticmethod
    def _format_issues_summary(issues: list[FairnessIssueDetail]) -> str:
        if not issues:
            return "  (none)"
        lines: list[str] = []
        for i in issues:
            lines.append(
                f"  - {i.code.value} (severity={i.severity}): {i.description}"
            )
        return "\n".join(lines)

    # ------------------------------------------------------------------
    # JSON parsing helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _parse_llm_json(raw: str) -> dict | None:
        """Parse LLM JSON, stripping markdown code fences if needed. Same
        defensive scheme as the other agents in this codebase."""
        if not raw or not isinstance(raw, str):
            return None
        text = raw.strip()
        if text.startswith("```"):
            lines = [l for l in text.split("\n") if not l.strip().startswith("```")]
            text = "\n".join(lines).strip()
        try:
            result = json.loads(text)
        except json.JSONDecodeError:
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

    # ------------------------------------------------------------------
    # Safe fallback
    # ------------------------------------------------------------------

    def _safe_assessment(
        self,
        _code: str,
        reason: str,
        assessed_at: str,
    ) -> FairnessAssessment:
        """Returns a conservative 'requires human review' assessment."""
        return FairnessAssessment(
            fairness_passed=False,
            confidence=0.0,
            issues=[FairnessIssueDetail(
                code=FairnessIssueCode.UNSUPPORTED_REASONING,
                severity="high",
                description=reason,
                recommended_action="Route to a human reviewer; assessment failed.",
            )],
            recommendation=FairnessRecommendation.ESCALATE,
            requires_human_review=True,
            audit_details=FairnessAuditDetail(
                evidence_counts={},
                confidence_gap=None,
                passenger_confidence=None,
                driver_confidence=None,
                decision_confidence=0.0,
                policies_cited_in_decision=[],
                policies_retrieved=[],
                policies_uncited=[],
                hallucinated_policy_refs=[],
                policy_compliance_alignment="unknown",
                rationale_length_chars=0,
                rationale_cites_evidence=False,
                passenger_passenger_compliant=None,
                driver_passenger_compliant=None,
                verdict="unknown",
                semantic_review_used=False,
                semantic_review_skipped_reason="deterministic findings already require human review",
            ),
            assessed_at=assessed_at,
            reason=reason,
        )


# ======================================================================
# Module-level helpers
# ======================================================================


def _case_evidence_summary(context: dict | None) -> str:
    """Compact, line-per-item view of the platform records the decision rests on,
    so the semantic review can check a claim against the evidence itself."""
    if not isinstance(context, dict):
        return ""

    def clip(text: Any) -> str:
        s = " ".join(str(text).split())
        return s if len(s) <= _EVIDENCE_LINE_MAX_CHARS else s[:_EVIDENCE_LINE_MAX_CHARS] + "..."

    def section(title: str, lines: list[str]) -> list[str]:
        if not lines:
            return []
        extra = len(lines) - _EVIDENCE_LIST_MAX_ITEMS
        shown = lines[:_EVIDENCE_LIST_MAX_ITEMS] + ([f"  ... {extra} more"] if extra > 0 else [])
        return [title] + shown

    out: list[str] = []
    if context.get("reporter") or context.get("description"):
        out.append(f"Filed by: {context.get('reporter', '?')} -- {clip(context.get('description', ''))}")
    for key, title in (("trip", "Trip"), ("payment", "Payment"), ("platform_policy", "Case policy")):
        if context.get(key):
            out.append(f"{title}: {_truncate_dict(context[key], 700)}")
    events = [e for e in context.get("app_events") or [] if isinstance(e, dict)]
    out += section("App events:", [
        f"  {e.get('timestamp', '?')} {e.get('event_type', '?')}: {clip(e.get('details', ''))}" for e in events])
    chats = [c for c in context.get("chat_log") or [] if isinstance(c, dict)]
    out += section("Chat log:", [
        f"  {c.get('timestamp', '?')} {c.get('sender', '?')} ({c.get('message_type', 'message')}): "
        f"{clip(c.get('message', c.get('content', '')))}" for c in chats])
    uploads = [u for u in context.get("evidence") or [] if isinstance(u, dict)]
    out += section("Uploaded evidence:", [f"  {clip(u)}" for u in uploads])
    findings = [f for f in context.get("findings") or [] if isinstance(f, dict)]
    out += section("Collector findings (deterministic checks):", [
        f"  [{f.get('kind', 'fact')}] {clip(f.get('statement', ''))}" for f in findings])
    return "\n".join(out)


def _truncate_dict(value: Any, max_len: int = 600) -> str:
    try:
        s = json.dumps(value, default=str)
    except Exception:
        s = str(value)
    if len(s) > max_len:
        s = s[:max_len] + "..."
    return s
