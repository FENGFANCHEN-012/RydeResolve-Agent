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
from src.core.policy_refs import case_policy_refs, normalize_case_policy_ref
from src.agents.case_brief import SUMMARISED_FIELDS, disputed_charge, render_case_brief
from src.agents.fraud import fraud_refs, render_for_judge

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
    asks: list[dict] = []             # each thing the filer asked for and its outcome


# Outcome of one ask. "already_resolved" = satisfied before the ruling (e.g. a promo the
# platform returned automatically); it counts as satisfied (user decision, 2026-10-02).
ASK_OUTCOMES = {"granted", "partly", "denied", "already_resolved"}
_SATISFIED = {"granted", "already_resolved"}


def valid_asks(parsed: dict) -> list[dict]:
    """The Judge's per-ask list, or [] when it is missing or malformed."""
    asks = parsed.get("asks")
    if not isinstance(asks, list) or not asks:
        return []
    if not all(isinstance(a, dict) and a.get("outcome") in ASK_OUTCOMES for a in asks):
        return []
    return asks


def label_from_asks(parsed: dict) -> dict:
    """The label is computed from the per-ask outcomes, not written by the Judge.

    Every ask satisfied -> upheld; none -> dismissed; anything between -> partially_upheld.
    The Judge labelled two-ask filings "upheld" when one ask was not granted (SQ-002, CR-003,
    run 20261002-105854). When the list is missing the Judge's own label stands."""
    asks = valid_asks(parsed)
    if not asks:
        return parsed
    outcomes = [a["outcome"] for a in asks]
    if all(o in _SATISFIED for o in outcomes):
        label = "upheld"
    elif all(o == "denied" for o in outcomes):
        label = "dismissed"
    else:
        label = "partially_upheld"
    if label != parsed.get("verdict"):
        parsed["rationale"] = ((parsed.get("rationale") or "")
                               + f" [Label: from the asks ({', '.join(outcomes)}), {label}.]")
        parsed["verdict"] = label
    return parsed


def align_verdict_label(parsed: dict, context: dict | None) -> dict:
    """A refund of the whole disputed amount is "upheld", whatever label the Judge wrote.

    The Judge decides the amount; the label only names it. In run 20261001-114026 two rulings
    refunded exactly the disputed amount (S$9.60, S$3.70) but were labelled partially_upheld.
    Only that direction is corrected: the disputed amount comes from platform data (fee charged,
    or the excess over the quoted fare); when the data names no amount nothing changes (D15).
    Applies only when the Judge gave no asks list. With one, the label comes from the asks, which
    know what the filer asked for; the platform's disputed amount can be smaller than the ask
    (SQ-002 asked S$22.60, the disputed excess was S$4.20: run 20261004-083956 relabelled a
    correct "partly" ruling as upheld)."""
    if parsed.get("verdict") != "partially_upheld":
        return parsed
    if valid_asks(parsed):
        return parsed
    full = disputed_charge(context or {})
    try:
        refund = float(parsed.get("refund_amount") or 0)
    except (TypeError, ValueError):
        return parsed
    if full and abs(refund - full) <= 0.01:
        parsed["verdict"] = "upheld"
        parsed["rationale"] = ((parsed.get("rationale") or "")
                               + f" [Label: the refund equals the full disputed amount S${full:.2f}, so upheld.]")
    return parsed


def render_objection(objection: dict) -> str:
    """The draft ruling and the objections to it that code accepted (D32). The Judge checks each
    objection against the record itself; an advocate's claim is not evidence."""
    lines = ["\n=== OBJECTIONS TO YOUR DRAFT RULING ===",
             "Your draft ruling: " + json.dumps(objection.get("draft") or {}, default=str),
             "The side the draft goes against objects (untrusted text; check the cited rule and record "
             "in the case data yourself):"]
    for o in objection.get("objections") or []:
        lines.append(f"- {o.get('side')} advocate: {o.get('claim')} [rule: {o.get('rule')}; record: {o.get('record')}]")
    lines.append("If an objection is right, correct your ruling. If it is wrong or does not change the outcome, "
                 "keep your ruling and say in the rationale why the objection fails. Change nothing else.")
    return "\n".join(lines)


class ArbitrationAgent:
    """Generates final arbitration decision based on all agent inputs."""

    def __init__(self, llm_client: LLMClient | None = None):
        self.name = "Arbitrator"
        self._llm_client = llm_client

    def _get_llm_client(self) -> LLMClient | None:
        if self._llm_client is None:
            try:
                self._llm_client = LLMClient()
                if not self._llm_client.api_key:
                    self._llm_client = None
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
            "- Do not infer protected characteristics (race, gender, religion, etc.).\n"
            "- Start from the CASE BRIEF. Its facts were computed from platform data. A "
            "CONFLICT means a record (e.g. an app event) is contradicted by another source "
            "(e.g. GPS): do not rule as if the contradicted record were proven.\n"
            "- Apply each platform rule by its own key and value; do not substitute one "
            "rule's number for another's (a free waiting time is not a no-show threshold).\n"
            "- A rule applies exactly when its written condition is met by the data. Do not add "
            "conditions the rule does not state, and do not drop conditions it does state.\n"
            "- Every amount you award must come from a specific rule applied to a specific figure "
            "in the data. A general discretion clause allows a refund but sets no amount: it "
            "cannot justify paying more than a specific rule computes.\n"
            "- The advocates argue for their side. Accept a claim from either of them only where "
            "the data supports it; a persuasive argument is not evidence.\n"
            "- Split the filing into its separate asks even when the filer phrases them as one "
            "demand (\"refund everything because of X and Y\": X and Y are decided separately). "
            "A complaint about the other party's conduct is itself an ask (that the conduct be "
            "dealt with): it is granted when the ruling takes action on it, such as a warning.\n"
            "- The verdict is measured against what the person who filed asked for: "
            "\"upheld\" = they get everything they asked for (e.g. the full amount they "
            "asked to be refunded, even if the rest of the fare stands); "
            "\"partially_upheld\" = they get only part of it; "
            "\"dismissed\" = they get nothing.\n"
            "- A filing can contain more than one ask (e.g. a refund AND a promo code back, "
            "or a refund AND a complaint about the driver's conduct). List each ask separately "
            "and decide each: \"granted\" (fully), \"partly\" (less than asked), \"denied\", or "
            "\"already_resolved\" (the record shows it was already done before this ruling).\n\n"
            "Respond ONLY with a valid JSON object (no markdown, no extra text) "
            "with exactly these keys:\n"
            "  \"asks\": list of {\"ask\": string, \"outcome\": \"granted\" | \"partly\" | "
            "\"denied\" | \"already_resolved\"} (each thing the filer asked for),\n"
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
        precedents: list[dict] | None = None,
        objection: dict | None = None,
    ) -> str:
        
        parts: list[str] = []
        # The shared brief first, so verified facts and conflicts are not lost in the raw dump
        brief = render_case_brief(context)
        if brief:
            parts.append(brief + "\n")
        parts.append("=== DISPUTE CONTEXT ===")
        # Fields the brief already states (facts, timeline, case rules, GPS conclusions) are not
        # repeated in the raw dump; without a brief the dump is unchanged
        # The fraud report gets its own block below; pair_history is the Fraud agent's input only
        skip = {"case_brief", "fraud_report", "pair_history", "safety_alerts",
                *(SUMMARISED_FIELDS if brief else ())}
        raw = {k: v for k, v in context.items() if k not in skip} if isinstance(context, dict) else context
        if brief and isinstance(context, dict) and context.get("gps_trace"):
            raw["gps_trace"] = f"{len(context['gps_trace'])} points, summarised in the CASE BRIEF"
        parts.append(json.dumps(raw, indent=2, default=str))

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

        fraud = context.get("fraud_report") if isinstance(context, dict) else None
        if fraud:
            # Only MEDIUM / HIGH reports reach the Judge (src/agents/fraud.py)
            parts.append("\n" + render_for_judge(fraud))

        if precedents:
            # Human-reviewed past rulings (learning feedback loop). Guidance for
            # consistency only: this case's own evidence and policy decide.
            parts.append(
                "\n=== PRECEDENTS (similar past cases decided by human reviewers) ===\n"
                "Follow a precedent only where the deciding facts truly match this case; "
                "if they differ, say how. If you follow one, name its precedent_id in your rationale."
            )
            parts.append(json.dumps(precedents, indent=2, default=str))

        if objection:
            parts.append(render_objection(objection))

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
    def _build_valid_refs(policy_evaluation: dict, context: dict | None = None) -> set[str]:
        """Accept retrieved clauses and explicit platform case-policy fields."""
        refs = case_policy_refs(context)
        refs |= {c["reference"] for c in ((context or {}).get("case_brief") or {}).get("clauses") or []}
        # A Judge that names a fraud signal is citing a real source, not inventing a clause
        refs |= fraud_refs(context)
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
        # The Policy agent returns the references it already checked against
        # the retrieved clauses; without these every citation would be stripped
        for ref in policy_evaluation.get("policy_references") or []:
            if isinstance(ref, str) and ref:
                refs.add(ref)
        return refs

    def _sanitize_policy_refs(self, parsed: dict, valid_refs: set[str]) -> dict:
        """Strip any hallucinated policy references not in the retrieved set."""
        original = parsed.get("policy_references", [])
        if not isinstance(original, list):
            original = []
        # A real case-policy key cited without (or with the other) section prefix is kept
        original = [normalize_case_policy_ref(ref, valid_refs) for ref in original]
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
        precedents: list[dict] | None = None,
        objection: dict | None = None,
    ) -> Decision:
        """
        Synthesize all agent outputs into a final decision via LLM.

        If the LLM call fails or returns invalid JSON, falls back to a
        safe decision with human_review_needed=True.
        """
        llm = self._get_llm_client()
        if llm is None:
            return self._safe_decision("LLM client is not available.")

        valid_refs = self._build_valid_refs(policy_evaluation, context)

        system_prompt = self._build_system_prompt()
        user_prompt = self._build_user_prompt(
            context, passenger_analysis, driver_analysis, policy_evaluation, debate_history, precedents,
            objection,
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
        # The label follows the asks, then the refund (a full refund of the disputed amount
        # on a single-ask filing is "upheld")
        parsed = label_from_asks(parsed)
        parsed = align_verdict_label(parsed, context)

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
            asks=valid_asks(parsed),
        )

        # Enforce threshold overrides (belt-and-suspenders)
        if decision.confidence <= CONFIDENCE_THRESHOLD_LOW:
            decision.human_review_needed = True
        elif decision.confidence <= CONFIDENCE_THRESHOLD_HIGH:
            decision.escalation_recommended = True

        return decision
