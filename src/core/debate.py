"""
Multi-Agent Debate Engine

Facilitates adversarial debate between Passenger and Driver agents.
Both agents now produce structured JSON outputs with evidence grounding.
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
    1. Passenger Agent states position + evidence (structured JSON)
    2. Driver Agent states position + evidence (structured JSON)
    3. Policy Agent injects relevant clauses
    4. Each agent rebuts the other's argument (text)
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
        Each entry: {round, speaker, content, type}
        """
        history = []

        # Initial analysis from both sides (structured JSON)
        passenger_analysis = await self.passenger_agent.analyze(context)
        driver_analysis = await self.driver_agent.analyze(context)
        policy_eval = await self.policy_agent.evaluate_compliance(context)

        history.append({
            "round": 0,
            "speaker": "passenger",
            "type": "analysis",
            "content": passenger_analysis,
        })
        history.append({
            "round": 0,
            "speaker": "driver",
            "type": "analysis",
            "content": driver_analysis,
        })
        history.append({
            "round": 0,
            "speaker": "policy",
            "type": "evaluation",
            "content": policy_eval,
        })

        # Debate rounds (rebuttals as text)
        for round_num in range(1, self.max_rounds + 1):
            # Passenger rebuts driver's latest argument
            driver_arg = self._extract_argument(history, "driver", round_num)
            p_rebuttal = await self.passenger_agent.rebut(driver_arg, context)
            history.append({
                "round": round_num,
                "speaker": "passenger",
                "type": "rebuttal",
                "content": p_rebuttal,
            })

            # Driver rebuts passenger's latest argument
            passenger_arg = self._extract_argument(history, "passenger", round_num)
            d_rebuttal = await self.driver_agent.rebut(passenger_arg, context)
            history.append({
                "round": round_num,
                "speaker": "driver",
                "type": "rebuttal",
                "content": d_rebuttal,
            })

        return history

    @staticmethod
    def _extract_argument(history: list[dict], speaker: str, round_num: int) -> str:
        """
        Extract the latest argument from a speaker for rebuttal.

        For round 1, uses the initial analysis.
        For subsequent rounds, uses the previous rebuttal.
        """
        # Find the most recent entry from this speaker
        for entry in reversed(history):
            if entry["speaker"] == speaker:
                content = entry["content"]
                if isinstance(content, dict):
                    # Structured analysis: combine stance + reasoning
                    stance = content.get("stance", "")
                    reasoning = content.get("reasoning", "")
                    evidence = content.get("evidence", [])
                    parts = []
                    if stance:
                        parts.append(f"Stance: {stance}")
                    if reasoning:
                        parts.append(f"Reasoning: {reasoning}")
                    if evidence:
                        parts.append(f"Evidence: {', '.join(str(e) for e in evidence[:3])}")
                    return "\n".join(parts) if parts else str(content)
                return str(content)
        return ""
