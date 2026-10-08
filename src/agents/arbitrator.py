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
    fare_finding: str | None = None   # was the money charged owed? (D25)
    issue_rulings: list[dict] = []    # one ruling per contested issue I# from the debate (D25)
    remanded_for: list[str] = []      # problems the code checks sent back to the Judge once (D25)
    charge_causes: list[dict] = []    # causes of a charge above the quote, by party and share (D29)


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


# Was the money charged owed under this trip's rules? Decided before, and apart from, conduct (D25)
FARE_FINDINGS = {"charge_correct", "overcharged", "no_money_at_stake"}


def ruling_problems(parsed: dict, open_issues: list[str], excess: float | None = None) -> list[str]:
    """Contradictions and omissions in a ruling that code can see. Each one is sent back to the
    Judge once (remand); one still there after that sends the case to a person.

    - charge_correct with a refund: the Judge found the charge was owed, then refunded it anyway
      because of the driver's conduct or "discretion" (RD-002-I3 run 20261008-113816-s3b, ST-001
      run 20261008-130700-stress). Conduct is answered with a penalty, never with the fare.
    - overcharged with no refund: the finding and the amount disagree the other way.
    - an open issue from the debate with no ruling: the Judge skipped a contested point (ST-001:
      the detour began before the closure alert; the driver advocate said the opposite).
    Fields the Judge did not return are not checked, so older replies behave as before."""
    problems = []
    finding = parsed.get("fare_finding")
    try:
        refund = float(parsed.get("refund_amount") or 0)
    except (TypeError, ValueError):
        refund = 0.0
    if finding == "charge_correct" and refund > 0:
        problems.append(f"fare_finding is charge_correct but refund_amount is S${refund:.2f}. If the "
                        "charge was owed, the refund is 0 and any conduct breach goes to driver_penalty; "
                        "if part of it was not owed, the finding is overcharged.")
    elif finding == "overcharged" and refund <= 0:
        problems.append("fare_finding is overcharged but refund_amount is 0. Refund the part that was "
                        "not owed, or change the finding.")
    elif finding is not None and finding not in FARE_FINDINGS:
        problems.append(f"fare_finding must be one of {sorted(FARE_FINDINGS)}, not {finding!r}.")
    if open_issues:
        rulings = parsed.get("issue_rulings")
        ruled = ({str(r.get("issue")).strip("[] ") for r in rulings if isinstance(r, dict)}
                 if isinstance(rulings, list) else set())
        missing = [i for i in open_issues if i not in ruled]
        if missing:
            problems.append(f"No ruling on contested issue(s) {', '.join(missing)}. For each, say which "
                            "side the records support, citing the fact ids or E# items.")
    if excess:
        problems.extend(cause_problems(parsed.get("charge_causes")))
    return problems


# ---------------------------------------------------------------- charge causes (D29)
# On a charge above the quote the Judge lists what caused the extra amount and whose cause each
# one is; code computes the refund. On ST-001/ST-002 the Judge set the amount in one step and
# never asked what pushed the route past the metered-fallback threshold (D26, D28).
CAUSE_PARTIES = ("driver", "rider", "external", "platform")
REFUNDED_PARTIES = ("driver", "platform")   # the rider does not pay for these causes
_SHARE_TOLERANCE = 0.05
_MONEY_ASK = ("refund", "fare", "charge", "difference", "money", "$", "pay")


def fare_excess(context) -> float | None:
    """The amount charged above the quote, from platform data; None when the dispute is about a
    fee or the data names no excess (the causes list is then not asked for)."""
    from src.agents.case_brief import _finding_values
    fee = _finding_values(context, "fee_check.charged")
    if fee and fee.get("fee"):
        return None
    fare = _finding_values(context, "fare_check.quoted_vs_charged")
    if fare and (fare.get("difference") or 0) > 0:
        return round(float(fare["difference"]), 2)
    return None


def cause_problems(causes) -> list[str]:
    """What is wrong with a charge_causes list, as remand text; [] when it can be used."""
    need = ("List charge_causes: each cause of the extra amount, the party whose action or choice "
            "caused it (driver, rider, external, platform), its share of the extra amount, and the "
            "ids that show it. Shares add up to 1.")
    if not isinstance(causes, list) or not causes:
        return [need]
    problems = []
    if any(not isinstance(c, dict) or c.get("party") not in CAUSE_PARTIES for c in causes):
        problems.append(f"Every cause needs a party from {list(CAUSE_PARTIES)}.")
    try:
        total = sum(float(c.get("share")) for c in causes if isinstance(c, dict))
    except (TypeError, ValueError):
        total = -1.0
    if abs(total - 1.0) > _SHARE_TOLERANCE:
        problems.append(f"The shares in charge_causes add up to {total:.2f}, not 1.")
    if any(isinstance(c, dict) and not c.get("cites") for c in causes):
        problems.append("Every cause in charge_causes must cite the fact ids, E# items or records that show it.")
    return problems


def apply_causes(parsed: dict, excess: float | None) -> dict:
    """Set the refund from a valid charge_causes list: the excess times the share of the causes
    the rider does not pay for. The money asks and fare_finding follow the computed amount.
    An invalid or missing list leaves the ruling as it is (the checks send it back)."""
    causes = parsed.get("charge_causes")
    if not excess or cause_problems(causes):
        return parsed
    share = sum(float(c["share"]) for c in causes if c["party"] in REFUNDED_PARTIES)
    share = max(0.0, min(1.0, share / sum(float(c["share"]) for c in causes)))
    refund = round(excess * share, 2)
    stated = parsed.get("refund_amount")
    parsed["refund_amount"] = refund
    parsed["fare_finding"] = "overcharged" if refund > 0 else "charge_correct"
    for ask in parsed.get("asks") or []:
        if isinstance(ask, dict) and any(w in str(ask.get("ask", "")).lower() for w in _MONEY_ASK):
            # Only a contradiction is corrected: the filer may have asked for more than the excess
            if refund > 0 and ask.get("outcome") == "denied":
                ask["outcome"] = "partly"
            elif refund == 0 and ask.get("outcome") in ("granted", "partly"):
                ask["outcome"] = "denied"
    parsed["rationale"] = ((parsed.get("rationale") or "")
                           + f" [Refund computed from charge_causes: {share:.0%} of the S${excess:.2f} excess"
                           f" is driver or platform caused = S${refund:.2f}"
                           + (f"; the Judge had stated {stated}" if stated not in (None, refund) else "") + ".]")
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
            "\"already_resolved\" (the record shows it was already done before this ruling).\n"
            "- Decide the money apart from conduct. fare_finding: \"charge_correct\" = every dollar "
            "charged was owed under this trip's rules, so refund_amount is 0; \"overcharged\" = some or "
            "all of it was not owed, and refund_amount is the part not owed; \"no_money_at_stake\" = "
            "no charge is disputed. A conduct breach (rudeness, a threat, a rule broken that did not "
            "change what was owed) is answered with driver_penalty or other action. It never changes "
            "refund_amount, and a discretion clause does not turn it into a refund.\n"
            "- If the charge is above the quoted fare (the case brief's fare_check fact), list in "
            "charge_causes every cause of the extra amount and whose cause it is: \"driver\" (the "
            "driver's own choice or error), \"rider\" (something the rider asked for or did), "
            "\"external\" (a cause outside both parties that this trip's rules make billable, e.g. a "
            "road closure verified BEFORE the detour began), \"platform\" (an app or pricing error). "
            "Give each cause its share of the extra amount (shares add up to 1) and the ids that "
            "show it. A rule that switches the fare basis (e.g. a metered fallback) does not decide "
            "whose cause the extra distance was. Code computes the refund from these: the driver and "
            "platform shares are refunded, so set refund_amount to match.\n"
            "- If ISSUES AFTER THE DEBATE lists contested issues (I1, I2, ...), rule on every one in "
            "issue_rulings: which side the records support and why, citing fact ids or E# items. "
            "Check each advocate's account of times and order of events against the records.\n\n"
            "Respond ONLY with a valid JSON object (no markdown, no extra text) "
            "with exactly these keys:\n"
            "  \"asks\": list of {\"ask\": string, \"outcome\": \"granted\" | \"partly\" | "
            "\"denied\" | \"already_resolved\"} (each thing the filer asked for),\n"
            "  \"fare_finding\": \"charge_correct\" | \"overcharged\" | \"no_money_at_stake\",\n"
            "  \"issue_rulings\": list of {\"issue\": \"I#\", \"ruling\": string, \"cites\": list of ids} "
            "([] when no issue is contested),\n"
            "  \"charge_causes\": list of {\"cause\": string, \"party\": \"driver\" | \"rider\" | "
            "\"external\" | \"platform\", \"share\": float, \"cites\": list of ids} ([] when the "
            "charge is not above the quote),\n"
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
    ) -> str:
        
        parts: list[str] = []
        # The shared brief first, so verified facts and conflicts are not lost in the raw dump
        brief = render_case_brief(context)
        if brief:
            parts.append(brief + "\n")

        # Evidence pool: lookups either advocate asked for, numbered E<n> (D23)
        from src.core.evidence_pool import EvidencePool
        pool_text = EvidencePool.render_for_prompt(context.get("evidence_pool") if isinstance(context, dict) else getattr(context, "evidence_pool", None),
                                                full_last=None, max_items=20)  # the Judge reads every item in full
        if pool_text:
            parts.append(pool_text + "\n")

        parts.append("=== DISPUTE CONTEXT ===")
        # Fields the brief already states (facts, timeline, case rules, GPS conclusions) are not
        # repeated in the raw dump; without a brief the dump is unchanged
        # The fraud report gets its own block below; pair_history is the Fraud agent's input only
        skip = {"case_brief", "fraud_report", "pair_history", "safety_alerts", "evidence_pool",
                *(SUMMARISED_FIELDS if brief else ())}
        raw = {k: v for k, v in context.items() if k not in skip} if isinstance(context, dict) else context
        if brief and isinstance(context, dict) and context.get("gps_trace"):
            raw["gps_trace"] = f"{len(context['gps_trace'])} points, summarised in the CASE BRIEF"
        parts.append(json.dumps(raw, indent=2, default=str))

        ids = [e.get("id", f"D{i}") for i, e in enumerate(debate_history or [], 1)]

        def label(i: int) -> str:
            return f" [{ids[i]}]" if len(ids) > i else ""

        parts.append(f"\n=== PASSENGER ADVOCATE ANALYSIS{label(0)} ===")
        parts.append(json.dumps(passenger_analysis, indent=2, default=str))

        parts.append(f"\n=== DRIVER ADVOCATE ANALYSIS{label(1)} ===")
        parts.append(json.dumps(driver_analysis, indent=2, default=str))

        parts.append(f"\n=== POLICY EVALUATION (RAG){label(2)} ===")
        parts.append(json.dumps(policy_evaluation, indent=2, default=str))

        if debate_history:
            parts.append("\n=== DEBATE POOL (every turn, numbered; cite as [D#]) ===")
            for i, entry in enumerate(debate_history):
                head = f"\n--- [{ids[i]}] {entry.get('speaker')}, round {entry.get('round')} ---"
                if i < 3 and entry.get("round") == 0:
                    # The opening analyses are printed in full above; not repeated
                    parts.append(head + " (opening, shown above)")
                    continue
                parts.append(head)
                content = entry.get("content")
                parts.append(content if isinstance(content, str) else json.dumps(content, indent=2, default=str))
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

        # Agreed facts and open issues from the typed moves (D24 step 3)
        from src.core.moves import issue_summary, render_issue_summary
        issues_text = render_issue_summary(issue_summary(debate_history or []))
        if issues_text:
            parts.append("\n" + issues_text)

        parts.append(
            "\n=== YOUR TASK ===\n"
            "Based on ALL of the above, produce the final arbitration decision. "
            "Weigh the evidence from both sides, apply the relevant policies, "
            "and state your conclusion clearly with a confidence score. "
            "In the rationale, cite what the ruling rests on by id: verified fact ids from the case brief, "
            "[E#] items from the evidence pool (either side may have found them; weigh them the same), "
            "policy references, and the [D#] turns you accept or reject. Do not cite ids that are not shown."
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
        audit_feedback: list[str] | None = None,
        previous=None,
    ) -> Decision:
        """
        Synthesize all agent outputs into a final decision via LLM.

        audit_feedback / previous: the Fairness audit found the previous ruling inconsistent and
        sent it back once (D27); the Judge sees its earlier ruling and the findings.

        If the LLM call fails or returns invalid JSON, falls back to a
        safe decision with human_review_needed=True.
        """
        llm = self._get_llm_client()
        if llm is None:
            return self._safe_decision("LLM client is not available.")

        valid_refs = self._build_valid_refs(policy_evaluation, context)

        system_prompt = self._build_system_prompt()
        user_prompt = self._build_user_prompt(
            context, passenger_analysis, driver_analysis, policy_evaluation, debate_history, precedents
        )
        if audit_feedback:
            prev = previous.model_dump(mode="json") if hasattr(previous, "model_dump") else previous
            user_prompt += (
                "\n\n=== FAIRNESS AUDIT OF YOUR PREVIOUS RULING ===\n"
                "Your previous ruling:\n" + json.dumps(prev, indent=1, default=str)
                + "\nThe audit found these inconsistencies:\n" + "\n".join(f"- {f}" for f in audit_feedback)
                + "\nReconsider. Either correct the ruling, or keep it and say in the rationale exactly "
                "why each finding does not change the outcome. Do not change a point the audit did not "
                "question.")

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

        # Code checks; a ruling that fails one goes back to the Judge once (remand, D25)
        from src.core.moves import issue_summary
        open_issues = [c["id"] for c in issue_summary(debate_history or [])["contested"] if c.get("id")]
        # On a charge above the quote, the refund is computed from the causes (D29)
        excess = fare_excess(context)
        parsed = apply_causes(parsed, excess)
        remanded_for = ruling_problems(parsed, open_issues, excess)
        if remanded_for:
            remand = ("Your ruling has these problems:\n" + "\n".join(f"- {p}" for p in remanded_for)
                      + "\nReturn the complete corrected JSON object with the same keys.")
            try:
                raw2 = await llm.chat_json(
                    messages=[
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_prompt},
                        {"role": "assistant", "content": raw if isinstance(raw, str) else json.dumps(raw)},
                        {"role": "user", "content": remand},
                    ],
                    temperature=0.2,
                )
                parsed2 = self._parse_llm_json(raw2)
            except Exception as exc:
                logger.warning("ArbitrationAgent remand call failed: %s", exc)
                parsed2 = None
            if parsed2 is not None:
                parsed = apply_causes(parsed2, excess)
            still = ruling_problems(parsed, open_issues, excess)
            if still:
                parsed["human_review_needed"] = True
                parsed["rationale"] = ((parsed.get("rationale") or "")
                                       + " [CHECK: still inconsistent after one remand: " + " ".join(still) + "]")

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
            fare_finding=parsed.get("fare_finding") if parsed.get("fare_finding") in FARE_FINDINGS else None,
            issue_rulings=[r for r in parsed.get("issue_rulings") or [] if isinstance(r, dict)],
            remanded_for=remanded_for,
            charge_causes=[c for c in parsed.get("charge_causes") or [] if isinstance(c, dict)],
        )

        # Enforce threshold overrides (belt-and-suspenders)
        if decision.confidence <= CONFIDENCE_THRESHOLD_LOW:
            decision.human_review_needed = True
        elif decision.confidence <= CONFIDENCE_THRESHOLD_HIGH:
            decision.escalation_recommended = True

        return decision