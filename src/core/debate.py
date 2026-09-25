"""
Multi-Agent Debate Engine
Facilitates adversarial debate between Passenger and Driver agents.
"""
from src.agents.collector import DisputeContext
from src.agents.passenger import PassengerAgent
from src.agents.driver import DriverAgent
from src.agents.policy import PolicyAgent
from src.config import MAX_DEBATE_ROUNDS
from src.core.trace import step


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
        for round_num in range(1, self.max_rounds + 1):
            # Passenger rebuts driver's latest argument
            # Round 1: history[-1] is policy, so take the driver's initial analysis (-2).
            # Later rounds: history[-1] is the driver's latest rebuttal.
            last_driver = history[-2] if round_num == 1 else history[-1]
            driver_arg = last_driver["content"] if isinstance(last_driver["content"], str) else str(last_driver["content"])
            async with step("Passenger", f"Round {round_num}: passenger rebuttal",
                            {"rebutting": driver_arg}) as s:
                p_rebuttal = await self.passenger_agent.rebut(driver_arg, context)
                s["output"] = p_rebuttal
            _fail_if_daily_quota_exhausted(p_rebuttal)
            history.append({
                "round": round_num,
                "speaker": "passenger",
                "content": p_rebuttal,
            })

            # Driver rebuts passenger's latest argument
            async with step("Driver", f"Round {round_num}: driver rebuttal",
                            {"rebutting": p_rebuttal}) as s:
                d_rebuttal = await self.driver_agent.rebut(p_rebuttal, context)
                s["output"] = d_rebuttal
            _fail_if_daily_quota_exhausted(d_rebuttal)
            history.append({
                "round": round_num,
                "speaker": "driver",
                "content": d_rebuttal,
            })

        return history
