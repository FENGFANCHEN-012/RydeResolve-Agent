"""
Multi-Agent Debate Engine
Facilitates adversarial debate between Passenger and Driver agents.
"""
from src.agents.collector import DisputeContext
from src.agents.passenger import PassengerAgent
from src.agents.driver import DriverAgent
from src.agents.policy import PolicyAgent
from src.agents.query_planner import QueryPlanner
from src.agents.research import render_debate, research_turn
from src.config import ADVOCATE_RESEARCH, MAX_DEBATE_ROUNDS
from src.core.evidence_pool import EvidencePool
from src.core.llm_client import llm_client
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

    async def debate_with_context(self, context: DisputeContext) -> tuple[list[dict], DisputeContext]:
        """The debate, plus the context it ended with.

        Shared pools every turn reads (D23):
        - policy clauses: the case brief's clauses plus every topic either side asked for
        - evidence pool: lookups either side asked for, answered by Collector tools, numbered E<n>
        - debate pool: every turn, numbered D<n>, with its speaker and round
        Before each advocate turn the advocate may ask for more evidence and rules (research step),
        so a rebuttal can answer the other side's new evidence with evidence of its own."""
        history: list[dict] = []
        get_retriever = getattr(self.policy_agent, "_get_retriever", None)
        retriever = get_retriever() if get_retriever else None
        real_case = isinstance(context, DisputeContext)   # unit tests pass stand-ins

        def add_turn(round_num: int, speaker: str, content) -> None:
            history.append({"id": f"D{len(history) + 1}", "round": round_num,
                            "speaker": speaker, "content": content})

        seen_pool: dict[str, int] = {}   # pool size when each side last looked up

        async def research(side: str, round_num: int):
            nonlocal context
            if not ADVOCATE_RESEARCH or not real_case:
                return
            pool = context.evidence_pool or []
            if round_num > 0 and not any(i.get("source_agent") not in (side, "system")
                                         for i in pool[seen_pool.get(side, 0):]):
                # Nothing new from the other side since this side last looked: skip the call (D24)
                return
            seen_pool[side] = len(pool)
            title = f"{side.capitalize()} advocate: look up evidence" + (
                " (opening)" if round_num == 0 else f" (round {round_num})")
            async with step(side.capitalize(), title, {"sees": ["case brief", "evidence pool", "debate so far"]}) as s:
                context, record = await research_turn(side, context, llm_client, retriever,
                                                      round_num, render_debate(history))
                s["output"] = record
            seen_pool[side] = len(context.evidence_pool or [])
            _fail_if_daily_quota_exhausted(record.get("error") or "")

        # Rule-based seed lookups (no LLM): the obvious checks for this dispute type
        seed = await QueryPlanner(agent_name="system").auto_query(context) if real_case else []
        if seed:
            context.evidence_pool = EvidencePool.merge_pools(context.evidence_pool, seed)

        # Initial analysis from both sides
        sees = ["case brief", "evidence pool", "retrieved policy clauses"]
        await research("passenger", 0)
        async with step("Passenger", "Passenger advocate: opening analysis", {"sees": sees}) as s:
            passenger_analysis = await self.passenger_agent.analyze(context)
            s["output"] = passenger_analysis
        _fail_if_daily_quota_exhausted(passenger_analysis)
        await research("driver", 0)
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
                    context, requests, retriever or self.policy_agent._get_retriever())
                if added:
                    record_retrieval("requested", added)
                s["output"] = {"added": [f"{c.get('source')} > {c.get('section')}" for c in added]}

        # Entries 0-2 carry the analyses (the Judge and Fairness read them by position)
        add_turn(0, "passenger", passenger_analysis)
        add_turn(0, "driver", driver_analysis)
        add_turn(0, "policy", policy_eval)

        # Debate rounds: each side may look up more, then answers the other side's latest turn
        for round_num in range(1, self.max_rounds + 1):
            last_driver = history[-2] if round_num == 1 else history[-1]
            driver_arg = last_driver["content"] if isinstance(last_driver["content"], str) else str(last_driver["content"])
            await research("passenger", round_num)
            async with step("Passenger", f"Round {round_num}: passenger rebuttal",
                            {"rebutting": last_driver["id"]}) as s:
                p_rebuttal = await self.passenger_agent.rebut(
                    driver_arg, context, debate_so_far=render_debate(history))
                s["output"] = p_rebuttal
            _fail_if_daily_quota_exhausted(p_rebuttal)
            add_turn(round_num, "passenger", p_rebuttal)

            await research("driver", round_num)
            async with step("Driver", f"Round {round_num}: driver rebuttal",
                            {"rebutting": history[-1]["id"]}) as s:
                d_rebuttal = await self.driver_agent.rebut(
                    p_rebuttal, context, debate_so_far=render_debate(history))
                s["output"] = d_rebuttal
            _fail_if_daily_quota_exhausted(d_rebuttal)
            add_turn(round_num, "driver", d_rebuttal)

        return history, context
