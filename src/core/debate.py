"""
Multi-Agent Debate Engine
Facilitates adversarial debate between Passenger and Driver agents.
"""
import re

from src.agents.collector import DisputeContext
from src.agents.passenger import PassengerAgent
from src.agents.driver import DriverAgent
from src.agents.policy import PolicyAgent
from src.config import MAX_DEBATE_ROUNDS
from src.core.trace import record_retrieval, step
from src.agents.case_brief import add_requested_clauses, valid_requests


def _fail_if_daily_quota_exhausted(result) -> None:
    """Stop before subsequent agents spend requests on an incomplete debate."""
    if isinstance(result, str):
        details = result
    elif isinstance(result, dict):
        details = " ".join(
            str(result.get(key, "")) for key in ("reasoning", "reason", "error")
        )
    else:
        return
    details = details.lower()
    if "generaterequestsperday" in details or (
        ("tokens per day" in details or "tpd" in details)
        and ("429" in details or "rate_limit_exceeded" in details)
    ):
        raise RuntimeError(
            "AI provider daily quota exhausted; no reliable automated ruling was produced."
        )


# Triage (D24) may allow complex cases a second round. On main the advocates cannot find new
# evidence mid-debate, so a further round runs only if a side says it raised a new point.
NEW_POINT_INSTRUCTION = (
    "End with one last line, exactly 'NEW_POINT: yes' if this rebuttal raises a fact or argument "
    "not already made in the debate, otherwise exactly 'NEW_POINT: no'."
)
_NEW_POINT_LINE = re.compile(r"^\s*\**\s*NEW_POINT\s*:\s*\**\s*(yes|no)\b.*$", re.I | re.M)


def _extra(instruction: str) -> dict:
    """Pass the instruction only when there is one, so rebut() is called as before otherwise."""
    return {"extra_instruction": instruction} if instruction else {}


def split_new_point(rebuttal):
    """Strip the NEW_POINT tag (the other side and the Judge never see it) and read it.
    No tag (or not text) counts as a new point: a missing answer must not cut the debate short."""
    if not isinstance(rebuttal, str):
        return rebuttal, True
    tags = _NEW_POINT_LINE.findall(rebuttal)
    if not tags:
        return rebuttal, True
    return _NEW_POINT_LINE.sub("", rebuttal).strip(), tags[-1].lower() == "yes"



class DebateEngine:
    """
    Orchestrates multi-round adversarial debate:
    
    Round structure:
    1. Passenger Agent states position + evidence
    2. Driver Agent states position + evidence
    3. Policy Agent injects relevant clauses
    4. Each agent rebuts the other's argument
    5. Repeat up to MAX_DEBATE_ROUNDS
    """

    def __init__(self):
        self.passenger_agent = PassengerAgent()
        self.driver_agent = DriverAgent()
        self.policy_agent = PolicyAgent()
        self.max_rounds = MAX_DEBATE_ROUNDS

    async def debate(self, context: DisputeContext) -> list[dict]:
        """
        Run the full debate and return debate history.
        Each entry: {round, speaker, content, evidence}
        """
        history, _ = await self.debate_with_context(context)
        return history

    async def debate_with_context(self, context: DisputeContext,
                                  max_rounds: int | None = None) -> tuple[list[dict], DisputeContext]:
        """The debate, plus the context it ended with: clauses the advocates requested
        (policy_requests) are added to the shared case brief for the rebuttals and the Judge.

        max_rounds (triage, D24) caps the rebuttal rounds; None means MAX_DEBATE_ROUNDS. A round
        after the first runs only if a side said its last rebuttal raised a new point."""
        history = []

        # Initial analysis from both sides
        sees = ["dispute context", "retrieved policy clauses"]
        async with step("Passenger", "Passenger advocate: opening analysis", {"sees": sees}) as s:
            passenger_analysis = await self.passenger_agent.analyze(context)
            s["output"] = passenger_analysis
        _fail_if_daily_quota_exhausted(passenger_analysis)
        async with step("Driver", "Driver advocate: opening analysis", {"sees": sees}) as s:
            driver_analysis = await self.driver_agent.analyze(context)
            s["output"] = driver_analysis
        _fail_if_daily_quota_exhausted(driver_analysis)
        async with step("Policy", "Policy compliance check (RAG)", {"sees": sees}) as s:
            policy_eval = await self.policy_agent.evaluate_compliance(context)
            s["output"] = policy_eval
        _fail_if_daily_quota_exhausted(policy_eval)

        requests = {"passenger": valid_requests(passenger_analysis), "driver": valid_requests(driver_analysis)}
        if any(requests.values()):
            async with step("CaseBrief", "Fetch the policy topics the advocates asked for",
                            {"requests": requests}) as s:
                context, added = await add_requested_clauses(
                    context, requests, self.policy_agent._get_retriever())
                if added:
                    record_retrieval("requested", added)
                s["output"] = {"added": [f"{c.get('source')} > {c.get('section')}" for c in added]}

        history.append({
            "round": 0,
            "speaker": "passenger",
            "content": passenger_analysis,
        })
        history.append({
            "round": 0,
            "speaker": "driver",
            "content": driver_analysis,
        })
        history.append({
            "round": 0,
            "speaker": "policy",
            "content": policy_eval,
        })

        # Debate rounds
        rounds = max_rounds or self.max_rounds
        for round_num in range(1, rounds + 1):
            # Ask for the NEW_POINT tag only when another round could follow
            ask = NEW_POINT_INSTRUCTION if round_num < rounds else ""
            # Passenger rebuts driver's latest argument
            # Round 1: history[-1] is policy, so take the driver's initial analysis (-2).
            # Later rounds: history[-1] is the driver's latest rebuttal.
            last_driver = history[-2] if round_num == 1 else history[-1]
            driver_arg = last_driver["content"] if isinstance(last_driver["content"], str) else str(last_driver["content"])
            async with step("Passenger", f"Round {round_num}: passenger rebuttal",
                            {"rebutting": driver_arg}) as s:
                p_rebuttal = await self.passenger_agent.rebut(driver_arg, context, **_extra(ask))
                s["output"] = p_rebuttal
            _fail_if_daily_quota_exhausted(p_rebuttal)
            p_rebuttal, p_new = split_new_point(p_rebuttal)
            history.append({
                "round": round_num,
                "speaker": "passenger",
                "content": p_rebuttal,
            })

            # Driver rebuts passenger's latest argument
            async with step("Driver", f"Round {round_num}: driver rebuttal",
                            {"rebutting": p_rebuttal}) as s:
                d_rebuttal = await self.driver_agent.rebut(p_rebuttal, context, **_extra(ask))
                s["output"] = d_rebuttal
            _fail_if_daily_quota_exhausted(d_rebuttal)
            d_rebuttal, d_new = split_new_point(d_rebuttal)
            history.append({
                "round": round_num,
                "speaker": "driver",
                "content": d_rebuttal,
            })

            if ask and not (p_new or d_new):
                async with step("Debate", f"Stop after round {round_num}: no new point from either side",
                                {"max_rounds": rounds}) as s:
                    s["output"] = {"rounds_run": round_num}
                break

        return history, context
