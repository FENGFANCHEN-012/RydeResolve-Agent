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
from src.core.llm_client import LLMClient
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
        retrieved_refs = self._build_valid_refs(policy_evaluation)
        hallucinated_refs = sorted({r for r in cited_refs if r not in retrieved_refs})
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

        # (a) one side not considered
        if passenger_count == 0 and driver_count == 0:
            add_issue(
                FairnessIssueCode.ONE_SIDE_NOT_CONSIDERED,
                "Neither the passenger's nor the driver's evidence was considered.",
                severity="high",
                recommended_action="Escalate to a human reviewer before executing.",
            )
            requires_human = True
        elif passenger_count == 0 or driver_count == 0:
            missing = "driver" if passenger_count == 0 else "passenger"
            add_issue(
                FairnessIssueCode.ONE_SIDE_NOT_CONSIDERED,
                f"The {missing}'s evidence was not considered at all.",
                severity="high",
                recommended_action="Escalate to a human reviewer before executing.",
            )
            requires_human = True
        else:
            # (b) asymmetric evidence (only counts as asymmetry when both sides present)
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
                    severity="medium",
                    recommended_action="Confirm the lighter side received a fair chance to respond.",
                )

        # (c) large unexplained confidence imbalance
        confidence_gap = abs(passenger_conf - driver_conf)
        if passenger_count > 0 and driver_count > 0 and confidence_gap > _DEFAULT_FAIRNESS_CONFIDENCE_GAP:
            add_issue(
                FairnessIssueCode.LARGE_CONFIDENCE_GAP,
                (
                    f"Large unexplained confidence imbalance between sides: "
                    f"passenger={passenger_conf:.2f}, driver={driver_conf:.2f} "
                    f"(gap={confidence_gap:.2f})."
                ),
                severity="medium",
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
            # If passenger violated but decision is UPHELD, that may be fine;
            # if NO violations and decision is DISMISSED, that is fine. The
            # contradictory cases are:
            contradictions: list[str] = []
            if verdict_value == "upheld" and pc_field is False and dc_field is True:
                contradictions.append(
                    "Passenger is marked non-compliant while driver is compliant, "
                    "yet verdict is UPHELD — contradiction."
                )
            if verdict_value == "dismissed" and pc_field is True and dc_field is False:
                contradictions.append(
                    "Driver is marked non-compliant while passenger is compliant, "
                    "yet verdict is DISMISSED — contradiction."
                )
            for text in contradictions:
                add_issue(
                    FairnessIssueCode.INTERNAL_INCONSISTENCY,
                    text,
                    severity="high",
                    recommended_action="Reconcile compliance findings with the verdict before executing.",
                )
                requires_human = True

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
        user_prompt = self._build_semantic_user_prompt(
            dispute_id=dispute_id,
            decision=decision,
            passenger_analysis=passenger_analysis,
            driver_analysis=driver_analysis,
            policy_evaluation=policy_evaluation,
            rationale=rationale,
            verdict_value=verdict_value,
            issues_so_far=issues_so_far,
        )

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
            return self._coerce_semantic_issues(parsed, retrieved_refs=self._build_valid_refs(policy_evaluation))
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
            '      "evidence_refs": list of strings (policy refs or '
            'debate round indices, may be empty)\n'
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
    ) -> str:
        return (
            f"Dispute ID: {dispute_id}\n"
            f"Verdict: {verdict_value}\n"
            f"Decision confidence: {getattr(decision, 'confidence', 0.0)}\n"
            f"Rationale: {rationale[:800]}\n\n"
            f"Cited policy refs: {list(getattr(decision, 'policy_references', []) or [])}\n\n"
            f"Passenger analysis (summary): "
            f"{_truncate_dict(passenger_analysis)}\n\n"
            f"Driver analysis (summary): "
            f"{_truncate_dict(driver_analysis)}\n\n"
            f"Policy evaluation (summary): "
            f"{_truncate_dict(policy_evaluation)}\n\n"
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
    ) -> list[FairnessIssueDetail]:
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
            # Keep only refs that actually exist in retrieval, to prevent
            # prompt-injection style fabrication.
            refs = [r for r in refs if r in retrieved_refs]
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
    def _build_valid_refs(policy_evaluation: dict) -> set[str]:
        """Extract valid policy references from the RAG output (same scheme
        as ``ArbitrationAgent._build_valid_refs``)."""
        refs: set[str] = set()
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
        if any(
            i.code in (
                FairnessIssueCode.NO_POLICY_SUPPORT,
                FairnessIssueCode.ONE_SIDE_NOT_CONSIDERED,
                FairnessIssueCode.INTERNAL_INCONSISTENCY,
                FairnessIssueCode.LOW_DECISION_CONFIDENCE,
            )
            for i in high
        ):
            return FairnessRecommendation.ESCALATE, False
        if medium:
            return FairnessRecommendation.AMEND_RECOMMENDED, False
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


def _truncate_dict(value: Any, max_len: int = 600) -> str:
    try:
        s = json.dumps(value, default=str)
    except Exception:
        s = str(value)
    if len(s) > max_len:
        s = s[:max_len] + "..."
    return s
