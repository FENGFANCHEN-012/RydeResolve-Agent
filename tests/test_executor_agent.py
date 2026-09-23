"""
Tests for ExecutionAgent — simulated execution + multilingual notifications.

These tests run completely offline. They exercise:
  a) successful refund
  b) compensation
  c) driver penalty
  d) human-review escalation
  e) no-action decision
  f) notification generation (en/zh/ms/ta)
  +) result schema, language fallback, error handling.
"""
import sys

import pytest

sys.path.insert(0, ".")

from src.agents.arbitrator import Decision, Verdict
from src.agents.executor import ExecutionAgent


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_decision(**overrides) -> Decision:
    """Create a Decision with sensible defaults; override per-test."""
    defaults = dict(
        verdict=Verdict.PARTIALLY_UPHELD,
        confidence=0.85,
        rationale=(
            "GPS trace and chat evidence support a partial refund for the "
            "overcharged amount."
        ),
        refund_amount=None,
        compensation=None,
        driver_penalty=None,
        human_review_needed=False,
        escalation_recommended=False,
    )
    defaults.update(overrides)
    return Decision(**defaults)


def required_keys_present(result: dict) -> bool:
    expected = {
        "dispute_id",
        "executed",
        "status",
        "notifications_sent",
        "actions_taken",
        "transaction_records",
        "notifications",
    }
    return expected.issubset(set(result.keys()))


# ---------------------------------------------------------------------------
# Schema / basic shape tests
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_result_has_required_keys():
    agent = ExecutionAgent()
    result = await agent.execute(make_decision(), "DSP-1")

    assert required_keys_present(result)
    assert result["dispute_id"] == "DSP-1"
    assert isinstance(result["actions_taken"], list)
    assert isinstance(result["transaction_records"], list)
    assert isinstance(result["notifications"], list)
    assert isinstance(result["executed"], bool)
    assert isinstance(result["notifications_sent"], bool)


@pytest.mark.asyncio
async def test_execute_does_not_crash_on_minimal_decision():
    agent = ExecutionAgent()
    decision = Decision(
        verdict=Verdict.DISMISSED,
        confidence=0.5,
        rationale="Insufficient evidence to uphold the dispute.",
    )
    result = await agent.execute(decision, "DSP-MIN")

    assert required_keys_present(result)
    # No optional fields set -> no financial actions recorded.
    assert result["transaction_records"] == []


# ---------------------------------------------------------------------------
# (a) Refund handling
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_successful_refund_creates_transaction():
    agent = ExecutionAgent()
    decision = make_decision(refund_amount=12.50)

    result = await agent.execute(decision, "DSP-RF1")

    assert result["status"] == "executed"
    assert result["executed"] is True

    refunds = [t for t in result["transaction_records"] if t["type"] == "refund"]
    assert len(refunds) == 1
    refund = refunds[0]
    assert refund["status"] == "simulated_success"
    assert refund["amount"] == 12.50
    assert refund["currency"] == "SGD"
    assert "simulated" in refund["note"].lower()

    # Human-readable entry
    assert any("Refund SGD 12.50" in action for action in result["actions_taken"])


@pytest.mark.asyncio
async def test_zero_refund_amount_is_ignored():
    agent = ExecutionAgent()
    decision = make_decision(refund_amount=0.0)

    result = await agent.execute(decision, "DSP-RF0")

    assert result["transaction_records"] == []
    assert not any("Refund" in a for a in result["actions_taken"])


@pytest.mark.asyncio
async def test_none_refund_amount_is_ignored():
    agent = ExecutionAgent()
    decision = make_decision(refund_amount=None)

    result = await agent.execute(decision, "DSP-RFN")

    assert result["transaction_records"] == []
    assert not any("Refund" in a for a in result["actions_taken"])


# ---------------------------------------------------------------------------
# (b) Compensation handling
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_compensation_is_recorded_and_value_preserved():
    agent = ExecutionAgent()
    decision = make_decision(compensation="SGD 10 voucher for inconvenience")

    result = await agent.execute(decision, "DSP-COMP")

    assert result["status"] == "executed"

    comps = [t for t in result["transaction_records"] if t["type"] == "compensation"]
    assert len(comps) == 1
    assert comps[0]["value"] == "SGD 10 voucher for inconvenience"
    assert comps[0]["status"] == "simulated_success"

    assert any(
        "Issue compensation" in a and "SGD 10 voucher" in a
        for a in result["actions_taken"]
    )


@pytest.mark.asyncio
async def test_empty_compensation_string_is_ignored():
    agent = ExecutionAgent()
    decision = make_decision(compensation="   ")

    result = await agent.execute(decision, "DSP-COMP-E")

    assert result["transaction_records"] == []
    assert not any("compensation" in a.lower() for a in result["actions_taken"])


# ---------------------------------------------------------------------------
# (c) Driver penalty handling
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_driver_penalty_is_recorded_structurally():
    agent = ExecutionAgent()
    decision = make_decision(driver_penalty="formal_warning")

    result = await agent.execute(decision, "DSP-PEN")

    assert result["status"] == "executed"

    penalties = [t for t in result["transaction_records"] if t["type"] == "driver_penalty"]
    assert len(penalties) == 1
    assert penalties[0]["value"] == "formal_warning"
    assert penalties[0]["status"] == "simulated_success"

    assert any(
        "Apply driver penalty" in a and "formal_warning" in a
        for a in result["actions_taken"]
    )


@pytest.mark.asyncio
async def test_driver_penalty_none_is_ignored():
    agent = ExecutionAgent()
    decision = make_decision(driver_penalty=None)

    result = await agent.execute(decision, "DSP-PEN-N")

    assert result["transaction_records"] == []
    assert not any("driver penalty" in a.lower() for a in result["actions_taken"])


# ---------------------------------------------------------------------------
# (d) Human review escalation
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_human_review_blocks_financial_actions():
    agent = ExecutionAgent()
    decision = make_decision(
        refund_amount=99.0,
        compensation="VIP voucher",
        driver_penalty="ban",
        human_review_needed=True,
    )

    result = await agent.execute(decision, "DSP-ESC")

    # Status is escalated, NOT executed.
    assert result["status"] == "escalated_to_human"
    assert result["executed"] is False

    # No financial / penalty transactions were created.
    assert result["transaction_records"] == []

    # The escalation line is recorded.
    assert "Escalated to human review queue" in result["actions_taken"]

    # Notifications may still be generated for both parties.
    assert len(result["notifications"]) >= 2
    for note in result["notifications"]:
        assert note["status"] == "simulated_sent"
    assert result["notifications_sent"] is True


# ---------------------------------------------------------------------------
# (e) No-action decision
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_no_action_decision_is_executed_with_no_records():
    agent = ExecutionAgent()
    decision = Decision(
        verdict=Verdict.DISMISSED,
        confidence=0.92,
        rationale="The driver's explanation is consistent with evidence.",
    )

    result = await agent.execute(decision, "DSP-NOOP")

    assert result["status"] == "executed"
    assert result["executed"] is True
    # No financial actions to take.
    assert result["transaction_records"] == []
    # Notifications still go out explaining the dismissal.
    assert len(result["notifications"]) == 2
    assert result["notifications_sent"] is True


# ---------------------------------------------------------------------------
# (f) Notification generation
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_notifications_default_to_english():
    agent = ExecutionAgent()
    result = await agent.execute(make_decision(), "DSP-NOTIF-EN")

    assert result["notifications_sent"] is True
    recipients = {n["recipient"] for n in result["notifications"]}
    assert recipients == {"passenger", "driver"}
    for n in result["notifications"]:
        assert n["language"] == "en"
        assert n["status"] == "simulated_sent"
        assert n["subject"]
        assert n["message"]
        # Sanity check: English strings reference the dispute id.
        assert "DSP-NOTIF-EN" in n["subject"] or "DSP-NOTIF-EN" in n["message"]


@pytest.mark.asyncio
@pytest.mark.parametrize("language", ["zh", "ms", "ta"])
async def test_notifications_support_non_english_languages(language):
    agent = ExecutionAgent()
    result = await agent.execute(make_decision(), "DSP-LANG", language=language)

    assert result["notifications_sent"] is True
    assert len(result["notifications"]) == 2
    for n in result["notifications"]:
        assert n["language"] == language
        assert n["status"] == "simulated_sent"
        assert n["subject"]
        assert n["message"]


@pytest.mark.asyncio
async def test_unknown_language_falls_back_to_english():
    agent = ExecutionAgent()
    result = await agent.execute(make_decision(), "DSP-XL", language="fr")

    for n in result["notifications"]:
        assert n["language"] == "en"
        assert n["status"] == "simulated_sent"


@pytest.mark.asyncio
async def test_escalation_notifications_use_escalation_template():
    agent = ExecutionAgent()
    decision = make_decision(human_review_needed=True)
    result = await agent.execute(decision, "DSP-ESC-NOTIF")

    assert len(result["notifications"]) == 2
    for n in result["notifications"]:
        assert "escalat" in n["subject"].lower() or "人工" in n["subject"] \
            or "dinaikkan" in n["subject"].lower() \
            or "மனித" in n["subject"]


# ---------------------------------------------------------------------------
# Simulated-only safety guard
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_all_transactions_are_labelled_simulated():
    agent = ExecutionAgent()
    decision = make_decision(
        refund_amount=5.0,
        compensation="Apology voucher",
        driver_penalty="warning",
    )
    result = await agent.execute(decision, "DSP-SIM")

    assert result["transaction_records"], "expected simulated records"
    for record in result["transaction_records"]:
        assert record["status"] == "simulated_success"
        assert "Simulated" in record["note"]

    for note in result["notifications"]:
        assert note["status"] == "simulated_sent"


# ---------------------------------------------------------------------------
# Combined scenario
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_combined_refund_compensation_and_penalty():
    agent = ExecutionAgent()
    decision = make_decision(
        refund_amount=8.0,
        compensation="SGD 5 voucher",
        driver_penalty="training reminder",
    )
    result = await agent.execute(decision, "DSP-ALL")

    types = {t["type"] for t in result["transaction_records"]}
    assert types == {"refund", "compensation", "driver_penalty"}

    assert result["executed"] is True
    assert result["status"] == "executed"


# ---------------------------------------------------------------------------
# Error handling
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_invalid_refund_amount_does_not_crash(monkeypatch):
    """A non-numeric refund_amount must be logged and skipped, not crash."""
    agent = ExecutionAgent()

    # Patch the attribute on the Decision instance only — Decision model uses
    # float | None, so we bypass validation by writing to __dict__ directly.
    decision = make_decision()
    object.__setattr__(decision, "refund_amount", "not-a-number")

    result = await agent.execute(decision, "DSP-BAD")

    # Execution completes with no refund transaction but a recorded skip.
    assert result["status"] == "executed"
    assert all(t["type"] != "refund" for t in result["transaction_records"])
    assert any("Skipped refund" in a for a in result["actions_taken"])