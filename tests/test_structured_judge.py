"""D29: on a charge above the quote the Judge lists causes by party; code computes the refund."""
import json

import pytest

from src.agents.arbitrator import ArbitrationAgent, apply_causes, cause_problems, fare_excess, ruling_problems

EXCESS_CTX = {"dispute_id": "D", "type": "route_deviation",
              "findings": [{"id": "fare_check.quoted_vs_charged", "kind": "fact", "value": {"difference": 17.5}}]}
FEE_CTX = {"dispute_id": "D", "type": "no_show",
           "findings": [{"id": "fee_check.charged", "kind": "fact", "value": {"fee": 8.0}}]}

CAUSES = [{"cause": "detour before the closure alert", "party": "driver", "share": 0.6,
           "cites": ["route_timing.vs_incident_alert"]},
          {"cause": "rider's 7-Eleven stop", "party": "rider", "share": 0.4, "cites": ["chat_log[2]"]}]


def test_excess_only_for_charges_above_the_quote():
    assert fare_excess(EXCESS_CTX) == 17.5
    assert fare_excess(FEE_CTX) is None
    assert fare_excess({"findings": []}) is None


def test_refund_is_the_driver_and_platform_share_of_the_excess():
    parsed = apply_causes({"refund_amount": 0, "fare_finding": "charge_correct", "rationale": "x",
                           "asks": [{"ask": "refund the difference", "outcome": "denied"},
                                    {"ask": "report the driver", "outcome": "granted"}],
                           "charge_causes": CAUSES}, 17.5)
    assert parsed["refund_amount"] == 10.5 and parsed["fare_finding"] == "overcharged"
    assert [a["outcome"] for a in parsed["asks"]] == ["partly", "granted"]
    assert "60% of the S$17.50 excess" in parsed["rationale"]


def test_all_rider_or_external_means_no_refund():
    causes = [{"cause": "verified closure", "party": "external", "share": 1.0, "cites": ["app_events[2]"]}]
    parsed = apply_causes({"refund_amount": 3.1, "asks": [{"ask": "refund", "outcome": "partly"}],
                           "charge_causes": causes}, 3.1)
    assert parsed["refund_amount"] == 0 and parsed["fare_finding"] == "charge_correct"
    assert parsed["asks"][0]["outcome"] == "denied"


def test_filer_asking_more_than_the_excess_keeps_partly():
    # SQ-002: asked S$22.60, the excess was S$4.20; a full refund of the excess is still "partly"
    causes = [{"cause": "unagreed detour", "party": "driver", "share": 1.0, "cites": ["route_check.distance"]}]
    parsed = apply_causes({"asks": [{"ask": "refund S$22.60", "outcome": "partly"}], "charge_causes": causes}, 4.2)
    assert parsed["refund_amount"] == 4.2 and parsed["asks"][0]["outcome"] == "partly"


def test_bad_cause_lists_are_problems_and_change_nothing():
    assert cause_problems(None) and cause_problems([])
    assert cause_problems([{**CAUSES[0], "party": "nobody"}, CAUSES[1]])
    assert cause_problems([{**CAUSES[0], "share": 0.9}, CAUSES[1]])          # adds up to 1.3
    assert cause_problems([{**CAUSES[0], "cites": []}, CAUSES[1]])
    assert cause_problems(CAUSES) == []
    bad = {"refund_amount": 5, "charge_causes": [{**CAUSES[0], "share": 0.9}, CAUSES[1]]}
    assert apply_causes(dict(bad), 17.5)["refund_amount"] == 5
    assert ruling_problems({"charge_causes": []}, [], excess=17.5)
    assert ruling_problems({"charge_causes": []}, []) == []   # no excess: not asked for


class SequenceLLM:
    def __init__(self, *replies):
        self.replies, self.calls = list(replies), []

    async def chat_json(self, messages, temperature=None):
        self.calls.append(messages)
        return self.replies.pop(0)


def ruling(**over):
    base = {"asks": [{"ask": "refund the difference", "outcome": "denied"}], "verdict": "dismissed",
            "confidence": 0.9, "refund_amount": 0, "compensation": None, "driver_penalty": None,
            "rationale": "metered fallback applies", "policy_references": [], "escalation_recommended": False,
            "human_review_needed": False, "fare_finding": "charge_correct", "issue_rulings": []}
    base.update(over)
    return json.dumps(base)


INPUTS = dict(context=EXCESS_CTX, passenger_analysis={}, driver_analysis={}, policy_evaluation={},
              debate_history=[])


@pytest.mark.asyncio
async def test_missing_causes_are_remanded_then_the_refund_is_computed():
    llm = SequenceLLM(ruling(), ruling(charge_causes=CAUSES, refund_amount=10.5, fare_finding="overcharged"))
    decision = await ArbitrationAgent(llm_client=llm).arbitrate(**INPUTS)
    assert len(llm.calls) == 2 and "charge_causes" in llm.calls[1][-1]["content"]
    assert decision.refund_amount == 10.5 and decision.verdict.value == "partially_upheld"
    assert decision.fare_finding == "overcharged" and len(decision.charge_causes) == 2
    assert not decision.human_review_needed


@pytest.mark.asyncio
async def test_a_matching_first_ruling_needs_one_call():
    llm = SequenceLLM(ruling(refund_amount=10.5, fare_finding="overcharged", charge_causes=CAUSES,
                             asks=[{"ask": "refund the difference", "outcome": "partly"}]))
    decision = await ArbitrationAgent(llm_client=llm).arbitrate(**INPUTS)
    assert len(llm.calls) == 1 and decision.refund_amount == 10.5 and not decision.remanded_for


@pytest.mark.asyncio
async def test_amount_that_contradicts_the_causes_is_sent_back_not_overridden():
    # RD-002-I3 in run 20261008-211749-d29: refund S$3.10 stated, causes all external
    fixed = ruling(refund_amount=10.5, fare_finding="overcharged", charge_causes=CAUSES, asks=[{"ask": "refund the difference", "outcome": "partly"}])
    llm = SequenceLLM(ruling(refund_amount=17.5, charge_causes=CAUSES), fixed)
    decision = await ArbitrationAgent(llm_client=llm).arbitrate(**INPUTS)
    assert len(llm.calls) == 2 and "give a refund of S$10.50" in llm.calls[1][-1]["content"]
    assert decision.refund_amount == 10.5 and not decision.human_review_needed


@pytest.mark.asyncio
async def test_mismatch_left_after_remand_uses_the_causes_without_escalating():
    bad = ruling(refund_amount=17.5, fare_finding="overcharged", charge_causes=CAUSES)
    llm = SequenceLLM(bad, bad)
    decision = await ArbitrationAgent(llm_client=llm).arbitrate(**INPUTS)
    assert decision.refund_amount == 10.5 and not decision.human_review_needed
    assert "the amount follows the causes" in decision.rationale and "the Judge had stated 17.5" in decision.rationale


@pytest.mark.asyncio
async def test_other_problems_left_after_remand_still_go_to_a_person():
    bad = ruling(refund_amount=17.5, charge_causes=[{**CAUSES[0], "share": 0.9}, CAUSES[1]])   # shares 1.3
    llm = SequenceLLM(bad, bad)
    decision = await ArbitrationAgent(llm_client=llm).arbitrate(**INPUTS)
    assert decision.human_review_needed and "[CHECK: still inconsistent" in decision.rationale
