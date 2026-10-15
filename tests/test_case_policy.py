"""Case policy keys as {value, text} (D36): values unchanged for code, scope text shown to agents."""
import json
import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from src.agents.case_brief import CaseBriefAgent, SUMMARISED_FIELDS, render_case_brief
from src.agents.collector import CollectorAgent, DisputeContext
from src.core.case_policy import policy_values, split_policy

ROOT = Path(__file__).resolve().parent.parent
SCOPE = "Binds the rider. A route the rider asks for must be agreed before the trip starts."


def test_split_accepts_both_formats():
    block = {"free_wait_time_min": 5,
             "rider_route_requests_must_be_agreed_before_trip": {"value": True, "text": SCOPE},
             "detour_billable_only_if": ["the rider agreed", "a verified road closure"],
             "_comment": "x"}
    values, texts = split_policy(block)
    assert values == {"free_wait_time_min": 5, "rider_route_requests_must_be_agreed_before_trip": True,
                      "detour_billable_only_if": ["the rider agreed", "a verified road closure"],
                      "_comment": "x"}
    assert texts == {"rider_route_requests_must_be_agreed_before_trip": SCOPE}
    assert split_policy(None) == (None, {})


def test_a_dict_value_that_is_not_a_wrapper_is_kept():
    # A rule whose own value is a mapping (e.g. fee caps by type) must not be unwrapped
    block = {"fee_caps_sgd": {"cleaning": 200, "waiting": 5}}
    assert policy_values(block) == block


@pytest.mark.asyncio
async def test_collector_keeps_values_and_texts(tmp_path):
    data = json.loads((ROOT / "data/mock_disputes/route_deviation_01.json").read_text(encoding="utf-8"))
    f = tmp_path / "d.json"
    f.write_text(json.dumps(data), encoding="utf-8")
    ctx = await CollectorAgent().collect_from_dataset(str(f))
    assert ctx.platform_policy["rider_route_requests_must_be_agreed_before_trip"] is True
    assert "rider" in ctx.platform_policy_text["rider_route_requests_must_be_agreed_before_trip"].lower()


class _NoRetriever:
    def retrieve_for_dispute(self, *a, **k):
        return []

    def retrieve(self, *a, **k):
        return []


@pytest.mark.asyncio
async def test_brief_shows_scope_next_to_value_and_judge_drops_raw_copy():
    ctx = DisputeContext(dispute_id="RD-X", type="route_deviation", reporter="passenger", order_id="R",
                         description="The driver took a longer road.",
                         platform_policy={"rider_route_requests_must_be_agreed_before_trip": True},
                         platform_policy_text={"rider_route_requests_must_be_agreed_before_trip": SCOPE})
    brief = await CaseBriefAgent(retriever=_NoRetriever()).build(ctx)
    assert brief["case_rules"] == {"platform_policy.rider_route_requests_must_be_agreed_before_trip": True}
    text = render_case_brief(ctx.model_copy(update={"case_brief": brief}))
    assert "platform_policy.rider_route_requests_must_be_agreed_before_trip = True\n    scope: " + SCOPE in text
    assert "platform_policy_text" in SUMMARISED_FIELDS


def test_every_case_key_has_a_text():
    glossary = json.loads((ROOT / "data/policies/case_rule_texts.json").read_text(encoding="utf-8"))
    for d in ("data/mock_disputes", "data/eval_cases/heldout", "data/eval_cases/stress_new",
              "data/eval_cases/fraud", "data/eval_cases/sealed"):
        for path in (ROOT / d).glob("*.json"):
            data = json.loads(path.read_text(encoding="utf-8"))
            for section in ("cancellation_policy", "platform_policy"):
                block = data.get(section)
                if not isinstance(block, dict):
                    continue
                _, texts = split_policy(block)
                missing = [k for k in block if not k.startswith("_") and k not in texts]
                assert not missing, f"{path.name}: {missing}"
                assert all(texts[k] == glossary[k] for k in texts), path.name
