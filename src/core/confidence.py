"""
Confidence Assessment Module
Evaluates verdict confidence based on evidence, policy alignment, and agent agreement.
"""

# Weights for confidence calculation
W_EVIDENCE = 0.4    # weight for evidence strength
W_POLICY = 0.35     # weight for policy alignment
W_AGREEMENT = 0.25  # weight for agent agreement


def calculate_confidence(
    evidence_strength: float,
    policy_alignment: float,
    agent_agreement: float,
) -> float:
    """
    Calculate confidence score.
    
    Args:
        evidence_strength: 0-1, strength of objective evidence (GPS, payment records)
        policy_alignment: 0-1, how well verdict aligns with platform policies
        agent_agreement: 0-1, consistency across agent conclusions
    
    Returns:
        confidence: 0-1
    """
    confidence = (
        W_EVIDENCE * evidence_strength
        + W_POLICY * policy_alignment
        + W_AGREEMENT * agent_agreement
    )
    return min(max(confidence, 0.0), 1.0)


def needs_human_review(confidence: float, threshold_low: float = 0.5) -> bool:
    """Check if the verdict needs human review."""
    return confidence <= threshold_low


def needs_escalation(confidence: float, threshold_high: float = 0.8) -> bool:
    """Check if the verdict should be flagged for random audit."""
    return confidence <= threshold_high
