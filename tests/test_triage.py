"""D24 step 2: triage grades complexity x risk from code signals only."""
from types import SimpleNamespace

from src.agents.collector import DisputeContext, DisputeType
from src.core.triage import COMPLEX_MAX_ROUNDS, triage


def ctx(brief=None, findings=None):
    return DisputeContext(dispute_id="T", type=DisputeType.NO_SHOW, reporter="driver",
                          order_id="O", description="x", case_brief=brief or {}, findings=findings or [])


def test_clean_case_is_simple_and_safe():
    g = triage(ctx({"conflicts": [], "gaps": []}), SimpleNamespace(urgency="P2"), {"level": "low"})
    assert (g["complexity"], g["risk"], g["max_rounds"], g["fairness_llm_audit"]) == ("simple", "safe", 1, False)


def test_conflict_or_fraud_makes_it_complex():
    g = triage(ctx({"conflicts": [{"id": "c"}]}), None, {"level": "low"})
    assert g["complexity"] == "complex" and g["max_rounds"] == COMPLEX_MAX_ROUNDS and g["fairness_llm_audit"]
    g = triage(ctx({}), None, {"level": "medium"})
    assert g["complexity"] == "complex" and "fraud risk medium" in g["reasons"]


def test_threat_makes_it_dangerous_even_when_simple():
    g = triage(ctx({}), SimpleNamespace(urgency="P1"), {"level": "low", "safety_alerts": [{"x": 1}]})
    assert g["complexity"] == "simple" and g["risk"] == "dangerous" and g["fairness_llm_audit"] is True


def test_large_disputed_amount_is_complex():
    from src.agents.collector_tools import Finding
    f = Finding(id="fee_check.charged", tool="fee_check", kind="fact", statement="s", value={"fee": 45.0})
    g = triage(ctx({}, [f]), None, {"level": "low"})
    assert g["complexity"] == "complex" and any("S$45.00" in r for r in g["reasons"])
