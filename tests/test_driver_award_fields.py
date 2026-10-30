"""D68: a driver's granted money ask must carry its amount in refund_amount, and the payout names
the driver (LT-06, LT-09, CC-06: the award was written as text or 0, so nothing was paid)."""
from types import SimpleNamespace

import pytest

from src.agents.code_judge import check_granted_money, review


def _decision(verdict="upheld", refund=None, asks=None, compensation=None):
    return SimpleNamespace(verdict=verdict, refund_amount=refund, compensation=compensation,
                           refund_calculation=None, decisive_facts=[{"fact": "x", "sources": [], "status": "verified"}],
                           asks=asks or [])


DRIVER = {"reporter": "driver", "trip": {}}


def test_granted_money_ask_with_amount_only_in_text_is_sent_back():
    d = _decision(asks=[{"ask": "Release the S$5 cancellation fee to the driver", "outcome": "granted"}],
                  compensation="S$5.00 released to driver as compensation")
    problems = check_granted_money(d, DRIVER)
    assert len(problems) == 1 and "refund_amount" in problems[0]
    assert problems[0] in review(d, DRIVER)


def test_other_partys_ask_does_not_hide_the_missing_award():
    # CC-06: the rider's wish not to pay listed as an ask, label partly, amount 0
    d = _decision("partially_upheld", 0.0, [
        {"ask": "Refund of S$35 cleaning fee charged to rider", "outcome": "denied"},
        {"ask": "Reimbursement of S$35 cleaning fee to driver", "outcome": "granted"}])
    assert "List only the driver's own asks" in check_granted_money(d, DRIVER)[0]


@pytest.mark.parametrize("d,ctx", [
    (_decision(refund=5.0, asks=[{"ask": "Release the S$5 fee", "outcome": "granted"}]), DRIVER),
    (_decision("dismissed", None, [{"ask": "Charge the rider S$35", "outcome": "denied"}]), DRIVER),
    (_decision(asks=[{"ask": "Warn the rider about the language used", "outcome": "granted"}]), DRIVER),
    (_decision(asks=[{"ask": "Return my S$5 promo code", "outcome": "granted"}]), {"reporter": "rider"}),
])
def test_no_problem_when_paid_denied_not_money_or_rider(d, ctx):
    assert check_granted_money(d, ctx) == []


def test_no_double_report_with_check_award():
    ctx = {"reporter": "driver", "trip": {"cleaning_fee_claimed": 35.0}}
    d = _decision(asks=[{"ask": "Charge the rider S$35", "outcome": "granted"}])
    assert check_granted_money(d, ctx) == []      # check_award already names it
    assert len([p for p in review(d, ctx) if "awards nothing" in p]) == 1


@pytest.mark.asyncio
async def test_driver_award_is_a_payment_to_the_driver():
    from src.agents.arbitrator import Decision, Verdict
    from src.agents.executor import ExecutionAgent
    result = {"actions_taken": [], "transaction_records": [], "dispute_id": "X"}
    d = Decision(verdict=Verdict.UPHELD, confidence=0.9, refund_amount=5.0, rationale="r")
    ExecutionAgent()._apply_refund(d, result, "driver")
    assert result["transaction_records"][0]["type"] == "driver_payment"
    assert "to driver" in result["actions_taken"][0]
    result = {"actions_taken": [], "transaction_records": [], "dispute_id": "X"}
    ExecutionAgent()._apply_refund(d, result, "passenger")
    assert result["transaction_records"][0]["type"] == "refund"
