"""
Agent 3: Passenger Perspective Agent
Analyzes dispute from passenger's viewpoint.
"""
from src.agents.collector import DisputeContext


class PassengerAgent:
    """Advocates passenger perspective in the dispute."""

    def __init__(self):
        self.name = "Passenger"
        self.role = """You are a passenger rights advocate analyzing a ride-hailing dispute 
        on the Ryde platform. Analyze the situation from the passenger's perspective, 
        assess reasonableness of their claims, cite passenger protection rights, 
        and identify passenger responsibilities."""

    async def analyze(self, context: DisputeContext) -> dict:
        """
        Return passenger perspective analysis:
        - stance: passenger's position on the dispute
        - evidence: supporting evidence from passenger's side
        - obligations: what passenger should have done
        - remedy_requested: what passenger is asking for
        """
        # TODO: Integrate Hunyuan LLM with passenger advocate prompt
        pass

    async def rebut(self, opponent_argument: str, context: DisputeContext) -> str:
        """Rebut driver agent's argument in the debate."""
        # TODO: Generate counter-argument
        pass
