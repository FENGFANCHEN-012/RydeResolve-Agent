"""Case policy blocks in either format.

A case's policy block (cancellation_policy / platform_policy) maps a rule key to its value.
Since D36 a key may also carry a short text that states the rule's SCOPE (who it binds and
which event it governs), because a bare name plus value hid the scope: in eval case RD-002
`rider_route_requests_must_be_agreed_before_trip = true` was read as covering a detour the
driver chose, and no agent could check the reading against any text.

    old: {"no_show_threshold_min": 5}
    new: {"no_show_threshold_min": {"value": 5, "text": "Applies when ..."}}

Since D39 a numeric time rule may also carry a "check" (what code measures and how it compares,
see data/policies/case_rule_checks.json); code evaluates it, agents see the result.

Both formats are accepted everywhere. Code that computes with a rule (fee checks, the eval
charge cap) reads only the values; agents are shown value and text together.
"""
from __future__ import annotations


def _is_wrapped(v) -> bool:
    return isinstance(v, dict) and "value" in v and set(v) <= {"value", "text", "check"}


def split_policy(block) -> tuple[dict | None, dict]:
    """(values, texts) for a policy block. values keeps the old shape (key -> value) and is
    None when the block is missing; texts maps key -> scope text for keys that have one."""
    if not isinstance(block, dict):
        return block, {}
    values, texts = {}, {}
    for k, v in block.items():
        if _is_wrapped(v):
            values[k] = v["value"]
            if isinstance(v.get("text"), str) and v["text"].strip():
                texts[k] = v["text"].strip()
        else:
            values[k] = v
    return values, texts


def policy_checks(block) -> dict:
    """key -> check spec, for wrapped keys that carry one."""
    if not isinstance(block, dict):
        return {}
    return {k: v["check"] for k, v in block.items() if _is_wrapped(v) and isinstance(v.get("check"), dict)}


def policy_values(block):
    """The block in the old key -> value shape."""
    return split_policy(block)[0]


def case_policy_block(data: dict):
    """The policy block a case file uses (same precedence as the Collector)."""
    return data.get("cancellation_policy") or data.get("platform_policy")
