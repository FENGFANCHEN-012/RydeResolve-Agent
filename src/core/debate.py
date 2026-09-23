"""
Multi-Agent Debate Engine
Facilitates adversarial debate between Passenger and Driver agents.
"""
from src.agents.collector import DisputeContext
from src.agents.passenger import PassengerAgent
from src.agents.driver import DriverAgent
from src.agents.policy import PolicyAgent
from src.config import MAX_DEBATE_ROUNDS


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
        passenger_analysis = await self.passenger_agent.analyze(context)
        driver_analysis = await self.driver_agent.analyze(context)
        policy_eval = await self.policy_agent.evaluate_compliance(context)

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
            p_rebuttal = await self.passenger_agent.rebut(driver_arg, context)
            history.append({
                "round": round_num,
                "speaker": "passenger",
                "content": p_rebuttal,
            })

            # Driver rebuts passenger's latest argument
            d_rebuttal = await self.driver_agent.rebut(p_rebuttal, context)
            history.append({
                "round": round_num,
                "speaker": "driver",
                "content": d_rebuttal,
            })

        return history
