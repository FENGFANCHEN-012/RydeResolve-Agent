"""
Agent 6: Arbitration Agent
Synthesizes all perspectives, evidence, and policy into a final verdict.

The arbitrator is a neutral judge. It does not advocate for either side.
It weighs the evidence, the policy references, and the debate history,
then produces a decision with a confidence score and escalation flag.
"""
import json
import logging

from pydantic import BaseModel, Field
from enum import Enum

from src.config import CONFIDENCE_THRESHOLD_HIGH, CONFIDENCE_THRESHOLD_LOW, LLM_API_KEY
from src.core.llm_client import LLMClient

logger = logging.getLogger(__name__)


class Verdict(str, Enum):
    UPHELD = "upheld"                 # fully in favour of the reporter
    PARTIALLY_UPHELD = "partially_upheld"  # partial relief
    DISMISSED = "dismissed"           # no relief; reporter's claim rejected


class Decision(BaseModel):
    verdict: Verdict
    confidence: float = Field(ge=0.0, le=1.0)
    refund_amount: float | None = None
    compensation: str | None = None
    driver_penalty: str | None = None
    rationale: str
    policy_references: list[str] = []
    escalation_recommended: bool = False
    human_review_needed: bool = False


class ArbitrationAgent:
    """Generates final arbitration decision based on all agent inputs."""

    def __init__(self, llm_client: LLMClient | None = None):
        self.name = "Arbitrator"
        self._llm_client = llm_client

    def _get_llm_client(self) -> LLMClient | None:
        if self._llm_client is None:
            if not LLM_API_KEY:
                return None
            try:
                self._llm_client = LLMClient()
            except Exception as exc:
                logger.warning("Could not initialise LLMClient: %s", exc)
                self._llm_client = None  # type: ignore[assignment]
        return self._llm_client  # type: ignore[return-value]

    # ------------------------------------------------------------------
    # JSON parsing helpers (same pattern as passenger/driver agents)
    # ------------------------------------------------------------------

    @staticmethod
    def _parse_llm_json(raw: str) -> dict | None:
        """Parse LLM JSON response, stripping markdown fences."""
        if not raw or not isinstance(raw, str):
            return None
        text = raw.strip()
        if text.startswith("```"):
            lines = text.split("\n")
            lines = [l for l in lines if not l.strip().startswith("```")]
            text = "\n".join(lines).strip()
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            start = text.find("{")
            end = text.rfind("}")
            if start == -1 or end == -1 or end <= start:
                return None
            try:
                return json.loads(text[start : end + 1])
            except json.JSONDecodeError:
                return None

    @staticmethod
    def _clamp(value, low: float, high: float) -> float:
        try:
            v = float(value)
        except (TypeError, ValueError):
            return low
        return max(low, min(high, v))

    # ------------------------------------------------------------------
    # Prompt builders
    # ------------------------------------------------------------------

    @staticmethod
    def _build_system_prompt() -> str:
        return (
            "You are a neutral arbitrator in a ride-hailing dispute. "
            "Your job is to weigh ALL available evidence, BOTH advocate "
            "arguments, and the applicable policies, then produce a fair "
            "and evidence-grounded final decision.\n\n"
            "Rules:\n"
            "- You must NOT favour either the passenger or the driver by default.\n"
            "- Every claim in the decision MUST be backed by evidence from the "
            "  provided DisputeContext or the policy clauses.\n"
            "- Do NOT invent GPS records, chat messages, payment values, or policies.\n"
            "- Distinguish between what each side claims and what is actually verified.\n"
            "- The decision must cite specific policy references from the provided clauses.\n"
            "- If the evidence is insufficient or contradictory, assign low confidence "
            "  and recommend human review.\n"
            "- Do not expose chain-of-thought; return concise, readable reasoning only.\n"
            "- Do not infer protected characteristics (race, gender, religion, etc.).\n\n"
            "Respond ONLY with a valid JSON object (no markdown, no extra text) "
            "with exactly these keys:\n"
            "  \"verdict\": string (one of: \"upheld\", \"partially_upheld\", \"dismissed\"),\n"
            "  \"confidence\": float (0.0-1.0),\n"
            "  \"refund_amount\": float | null (refund in SGD, or null if none),\n"
            "  \"compensation\": string | null (textual description of compensation, or null),\n"
            "  \"driver_penalty\": string | null (textual penalty or warning, or null),\n"
            "  \"rationale\": string (concise, evidence-based reasoning),\n"
            "  \"policy_references\": list of strings (only from provided clauses),\n"
            "  \"escalation_recommended\": boolean (true if confidence is borderline),\n"
            "  \"human_review_needed\": boolean (true if evidence is too weak)"
        )

    @staticmethod
    def _build_user_prompt(
        context: dict,
        passenger_analysis: dict,
        driver_analysis: dict,
        policy_evaluation: dict,
        debate_history: list[dict],
    ) -> str:
        
        parts: list[str] = ["=== DISPUTE CONTEXT ==="]
        parts.append(json.dumps(context, indent=2, default=str))

        parts.append("\n=== PASSENGER ADVOCATE ANALYSIS ===")
        parts.append(json.dumps(passenger_analysis, indent=2, default=str))

        parts.append("\n=== DRIVER ADVOCATE ANALYSIS ===")
        parts.append(json.dumps(driver_analysis, indent=2, default=str))

        parts.append("\n=== POLICY EVALUATION (RAG) ===")
        parts.append(json.dumps(policy_evaluation, indent=2, default=str))

        if debate_history:
            parts.append("\n=== DEBATE HISTORY ===")
            for i, entry in enumerate(debate_history, 1):
                parts.append(f"\n--- Round {i} ---")
                parts.append(json.dumps(entry, indent=2, default=str))
        else:
            parts.append("\n=== DEBATE HISTORY ===\nNone")

        parts.append(
            "\n=== YOUR TASK ===\n"
            "Based on ALL of the above, produce the final arbitration decision. "
            "Weigh the evidence from both sides, apply the relevant policies, "
            "and state your conclusion clearly with a confidence score."
        )
        return "\n".join(parts)

    # ------------------------------------------------------------------
    # Safe fallback
    # ------------------------------------------------------------------

    def _safe_decision(self, reason: str) -> Decision:
        """Return a safe decision that escalates to human review."""
        return Decision(
            verdict=Verdict.DISMISSED,
            confidence=0.0,
            refund_amount=None,
            compensation=None,
            driver_penalty=None,
            rationale=reason,
            policy_references=[],
            escalation_recommended=True,
            human_review_needed=True,
        )

    # ------------------------------------------------------------------
    # Policy reference sanitisation (same pattern as passenger/driver)
    # ------------------------------------------------------------------

    @staticmethod
    def _build_valid_refs(policy_evaluation: dict) -> set[str]:
        """Extract valid policy references from the RAG output."""
        refs: set[str] = set()
        if not isinstance(policy_evaluation, dict):
            return refs
        # policy_evaluation may contain a "policies" or "chunks" list
        for key in ("policies", "chunks", "clauses"):
            items = policy_evaluation.get(key, [])
            if isinstance(items, list):
                for idx, item in enumerate(items):
                    if isinstance(item, dict):
                        source = item.get("source", "unknown")
                        chunk = item.get("chunk_index", idx)
                        refs.add(f"{source}#{chunk}")
        return refs

    def _sanitize_policy_refs(self, parsed: dict, valid_refs: set[str]) -> dict:
        """Strip any hallucinated policy references not in the retrieved set."""
        original = parsed.get("policy_references", [])
        if not isinstance(original, list):
            original = []
        clean = [ref for ref in original if ref in valid_refs]
        if len(clean) != len(original):
            dropped = len(original) - len(clean)
            parsed["rationale"] = (
                (parsed.get("rationale", "") or "")
                + f" [NOTE: {dropped} unverified policy reference(s) removed.]"
            )
            parsed["human_review_needed"] = True
        parsed["policy_references"] = clean
        return parsed

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def arbitrate(
        self,
        context: dict,
        passenger_analysis: dict,
        driver_analysis: dict,
        policy_evaluation: dict,
        debate_history: list[dict],
    ) -> Decision:
        """
        Synthesize all agent outputs into a final decision via LLM.

        If the LLM call fails or returns invalid JSON, falls back to a
        safe decision with human_review_needed=True.
        """
        llm = self._get_llm_client()
        if llm is None:
            return self._safe_decision("LLM client is not available.")

        valid_refs = self._build_valid_refs(policy_evaluation)

        system_prompt = self._build_system_prompt()
        user_prompt = self._build_user_prompt(
            context, passenger_analysis, driver_analysis, policy_evaluation, debate_history
        )

        # Call LLM
        try:
            raw = await llm.chat_json(
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                temperature=0.2,
            )
        except Exception as exc:
            logger.warning("ArbitrationAgent arbitrate LLM call failed: %s", exc)
            return self._safe_decision(f"LLM call failed: {exc}")

        # Parse JSON
        parsed = self._parse_llm_json(raw)
        if parsed is None:
            return self._safe_decision("LLM returned invalid JSON.")

        # Sanitise policy references
        parsed = self._sanitize_policy_refs(parsed, valid_refs)

        # Validate verdict
        verdict_str = parsed.get("verdict", "")
        try:
            verdict = Verdict(verdict_str)
        except ValueError:
            verdict = Verdict.DISMISSED
            parsed["human_review_needed"] = True
            parsed["rationale"] = (
                (parsed.get("rationale", "") or "")
                + f" [WARNING: invalid verdict '{verdict_str}', defaulting to dismissed.]"
            )

        confidence = self._clamp(parsed.get("confidence", 0.0), 0.0, 1.0)

        # Build Decision
        decision = Decision(
            verdict=verdict,
            confidence=confidence,
            refund_amount=parsed.get("refund_amount"),
            compensation=parsed.get("compensation"),
            driver_penalty=parsed.get("driver_penalty"),
            rationale=parsed.get("rationale", ""),
            policy_references=parsed.get("policy_references", []),
            escalation_recommended=bool(
                parsed.get("escalation_recommended", confidence <= CONFIDENCE_THRESHOLD_HIGH)
            ),
            human_review_needed=bool(
                parsed.get("human_review_needed", confidence <= CONFIDENCE_THRESHOLD_LOW)
            ),
        )

        # Enforce threshold overrides (belt-and-suspenders)
        if decision.confidence <= CONFIDENCE_THRESHOLD_LOW:
            decision.human_review_needed = True
        elif decision.confidence <= CONFIDENCE_THRESHOLD_HIGH:
            decision.escalation_recommended = True

        return decision