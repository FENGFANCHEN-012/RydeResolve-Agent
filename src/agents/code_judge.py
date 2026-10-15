"""Code Judge (D38): deterministic checks the Judge's draft must pass before it can execute.

The Judge (an LLM) decides WHAT the ruling rests on; code checks what can be checked:

1. Decisive facts. The Judge lists the facts its ruling turns on, each with the records it rests
   on and a status: "verified", "unverifiable" or "contradicted". A ruling that turns on a fact
   that is not verified cannot be automated. Code also cross-checks the Judge's own statuses:
   a fact marked "verified" whose record the Collector found contradicted or missing (a conflict
   or gap finding names it) is not verified.
2. The amount. Any refund comes with `refund_calculation`, plain arithmetic such as "60 - 40" or
   "4 * 1.20". Code evaluates it, checks it gives the refund, and checks that every number in it
   is a figure from the platform records (trip, payment, app events, findings, case policy; never
   the chat, where a party can type anything). A goodwill amount has no such calculation.

The checks never change a ruling. A failed check sends the draft back to the Judge once with the
problems; if the second draft still fails, the case goes to a person (human_review_needed). A second
draft that pays the same but just stops listing the questioned record also fails (D42).
Switched by CODE_JUDGE (on by default on this branch; CODE_JUDGE=0 for A/B runs).
"""
from __future__ import annotations

import ast
import operator
import os
import re

CODE_JUDGE = os.getenv("CODE_JUDGE", "1").strip().lower() not in ("0", "false", "no", "off")

FACT_STATUSES = ("verified", "unverifiable", "contradicted")
_NUM_RE = re.compile(r"\d+(?:\.\d+)?")
_DATE_TIME_RE = re.compile(r"\d{4}-\d{2}-\d{2}(?:[T ]\d{2}:\d{2}(?::\d{2})?(?:\.\d+)?)?(?:[+-]\d{2}:?\d{2}|Z)?"
                           r"|\b\d{1,2}:\d{2}(?::\d{2})?\b|\b[A-Z]+-[A-Z0-9-]*\d+\b")
_OPS = {ast.Add: operator.add, ast.Sub: operator.sub, ast.Mult: operator.mul, ast.Div: operator.truediv}


def _dump(o):
    return o.model_dump() if hasattr(o, "model_dump") else (o if isinstance(o, dict) else {})


def _findings(context: dict) -> list[dict]:
    return [_dump(f) for f in (context or {}).get("findings") or []]


def record_numbers(context: dict) -> set[float]:
    """Every number in the platform records, including numbers inside strings ("S$2.50 rate").
    Not the chat."""
    from src.core.case_policy import policy_values
    nums: set[float] = set()

    def walk(v):
        if isinstance(v, bool) or v is None:
            return
        if isinstance(v, (int, float)):
            nums.add(round(float(v), 2))
        elif isinstance(v, str):
            # Dates, times and ids are not amounts: "2026-10-09T07:53" would otherwise put 7, 9,
            # 10 and 53 among the figures and let any small constant pass
            v = _DATE_TIME_RE.sub(" ", v)
            nums.update(round(float(x), 2) for x in _NUM_RE.findall(v))
        elif isinstance(v, dict):
            for x in v.values():
                walk(x)
        elif isinstance(v, (list, tuple)):
            for x in v:
                walk(x)

    for section in ("trip", "payment", "app_events"):
        walk((context or {}).get(section))
    walk(policy_values((context or {}).get("platform_policy")))
    walk([f.get("value") for f in _findings(context)])
    return nums


def _eval_arith(expr: str) -> tuple[float | None, list[float]]:
    """Value of a plain arithmetic expression and the numbers in it; (None, []) if it is not one."""
    text = str(expr or "").replace("S$", "").replace("$", "").replace("x", "*").replace("×", "*")
    try:
        tree = ast.parse(text, mode="eval")
    except SyntaxError:
        return None, []
    literals: list[float] = []

    def ev(n):
        if isinstance(n, ast.Expression):
            return ev(n.body)
        if isinstance(n, ast.Constant) and isinstance(n.value, (int, float)) and not isinstance(n.value, bool):
            literals.append(float(n.value))
            return float(n.value)
        if isinstance(n, ast.BinOp) and type(n.op) in _OPS:
            return _OPS[type(n.op)](ev(n.left), ev(n.right))
        if isinstance(n, ast.UnaryOp) and isinstance(n.op, ast.USub):
            return -ev(n.operand)
        raise ValueError("not plain arithmetic")

    try:
        return round(ev(tree), 2), literals
    except (ValueError, ZeroDivisionError):
        return None, []


def _flagged(context: dict) -> dict[str, str]:
    """Records a conflict or gap finding calls into question -> the finding."""
    flagged: dict[str, str] = {}
    for f in _findings(context):
        if f.get("kind") in ("conflict", "gap"):
            for src in f.get("questioned") or f.get("sources") or []:
                flagged.setdefault(str(src), f"{f.get('kind')}: {f.get('statement')}")
    return flagged


def _verified_sources(decision) -> set[str]:
    return {str(src) for f in (getattr(decision, "decisive_facts", None) or [])
            if isinstance(f, dict) and str(f.get("status") or "").lower() == "verified"
            for src in f.get("sources") or []}


def _all_sources(decision) -> set[str]:
    return {str(src) for f in (getattr(decision, "decisive_facts", None) or [])
            if isinstance(f, dict) for src in f.get("sources") or []}


def _verdict(decision):
    v = getattr(decision, "verdict", None)
    return getattr(v, "value", v)


def check_remand(first, revised, context: dict) -> list[str]:
    """D42: the first draft was blocked because a decisive fact rested on a questioned record; a
    revised draft that pays the same verdict and amount but simply no longer lists that record still
    rests on it (SA-08: the Judge deleted app_events[8] and copied the rest). A changed ruling, or a
    record kept and marked as not verified, is left to the other checks."""
    try:
        refund = float(getattr(revised, "refund_amount", None) or 0)
        first_refund = float(getattr(first, "refund_amount", None) or 0)
    except (TypeError, ValueError):
        return []
    if refund <= 0 or abs(refund - first_refund) > 0.01 or _verdict(revised) != _verdict(first):
        return []
    blocked = _verified_sources(first) & set(_flagged(context))
    dropped = sorted(blocked - _all_sources(revised))
    if not dropped:
        return []
    return ["The revised ruling pays the same as the draft the code check blocked, but no longer lists "
            "the questioned record(s) " + ", ".join(dropped) + " it rested on; dropping a record does "
            "not remove what it was used for. A person decides."]


def rejects_own_claim(decision, context: dict) -> bool:
    """D50: the ruling rejects a driver's own cleaning / damage claim and pays nothing. Policy v2.1
    s4.4 rejects a claim whose photo evidence is insufficient (late, not linked to the trip), so a
    doubt about the driver's own photo is the reason to reject, not a reason for a person
    (OF-17: a photo 26 h late and 7.6 km away). Paying on a doubted photo is never allowed."""
    from src.core.governing_policy import is_property_case
    ctx = context or {}
    if str(ctx.get("reporter") or "").lower() != "driver" or not is_property_case(ctx):
        return False
    verdict = getattr(getattr(decision, "verdict", None), "value", getattr(decision, "verdict", None))
    try:
        refund = float(getattr(decision, "refund_amount", None) or 0)
    except (TypeError, ValueError):
        return False
    return verdict == "dismissed" and refund <= 0


def _photo_only(f: dict) -> bool:
    return bool(f.get("sources")) and all(str(s).startswith(("evidence[", "photo_checks.", "image_analysis."))
                                          for s in f.get("sources"))


def check_facts(decision, context: dict) -> list[str]:
    facts = [f for f in (getattr(decision, "decisive_facts", None) or []) if isinstance(f, dict)]
    if not facts:
        return ["The ruling lists no decisive facts: name the facts it turns on, their records and "
                "whether each is verified."]
    flagged = _flagged(context)
    rejecting = rejects_own_claim(decision, context)
    problems = []
    for f in facts:
        status = str(f.get("status") or "").lower()
        name = str(f.get("fact") or "?")[:160]
        if status not in FACT_STATUSES:
            problems.append(f"Decisive fact \"{name}\" has no valid status (verified / unverifiable / contradicted).")
            continue
        if rejecting and _photo_only(f):
            continue   # a doubt about the claimant's own photo is what rejects the claim (v2.1 s4.4)
        if status != "verified":
            problems.append(f"The ruling turns on a fact that is {status}: \"{name}\". "
                            "A ruling that rests on it cannot be automated.")
            continue
        for src in f.get("sources") or []:
            hit = flagged.get(str(src))
            if hit:
                problems.append(f"Decisive fact \"{name}\" is marked verified, but its record {src} is "
                                f"called into question by the platform data ({hit[:200]}).")
    return problems


def check_amount(decision, context: dict) -> list[str]:
    try:
        refund = float(getattr(decision, "refund_amount", None) or 0)
    except (TypeError, ValueError):
        return []
    if refund <= 0:
        return []
    calc = getattr(decision, "refund_calculation", None)
    if not calc:
        return [f"The refund S$%.2f has no refund_calculation: give the arithmetic from figures in the "
                f"records." % refund]
    value, literals = _eval_arith(calc)
    if value is None:
        return [f"refund_calculation \"{str(calc)[:120]}\" is not plain arithmetic on numbers."]
    problems = []
    if abs(value - refund) > 0.01:
        problems.append(f"refund_calculation \"{calc}\" gives S$%.2f, not the refund S$%.2f." % (value, refund))
    nums = record_numbers(context)
    stray = [x for x in literals if not any(abs(x - n) <= 0.005 for n in nums)]
    if stray:
        problems.append("refund_calculation uses numbers that are not figures in the platform records: "
                        + ", ".join(f"{x:g}" for x in stray)
                        + ". An amount set by discretion or goodwill is a person's decision.")
    return problems


def check_photos(decision, context: dict) -> list[str]:
    """D47: a photo in doubt (a conflict on evidence[i]: taken before the trip, edited, reused, not
    what it claims) is a possible fake, and that is a person's call whichever side the ruling favours.
    check_facts only catches a ruling that rests on the photo; IM-08 refunded the rider because the
    driver's photo predated the trip, which also settles the doubt about the driver by itself."""
    if getattr(decision, "human_review_needed", False) or rejects_own_claim(decision, context):
        return []
    doubted = {}
    for f in _findings(context):
        if f.get("kind") == "conflict":
            for src in f.get("questioned") or f.get("sources") or []:
                if str(src).startswith("evidence["):
                    doubted.setdefault(str(src), str(f.get("statement") or "")[:200])
    if not doubted:
        return []
    return ["The case has a photo in doubt (" + "; ".join(f"{k}: {v}" for k, v in sorted(doubted.items()))
            + "). Whichever side the ruling favours, a doubted photo is a person's decision: set "
            "human_review_needed to true."]


def check_route_refund(decision, context: dict) -> list[str]:
    """D50: Policy v2.1 s1.3 refunds a route deviation's excess DISTANCE fare, never tolls, time or
    surge. When the fare breakdown records that fare, a route refund above it is wrong (DISP-001,
    run 20261014-201340: S$6.50, the whole excess, instead of the recorded S$3.44)."""
    trip = (context or {}).get("trip") or {}
    fb = trip.get("fare_breakdown") if isinstance(trip.get("fare_breakdown"), dict) else {}
    edf = fb.get("excess_distance_fare")
    dtype = getattr((context or {}).get("type"), "value", (context or {}).get("type"))
    try:
        refund = float(getattr(decision, "refund_amount", None) or 0)
    except (TypeError, ValueError):
        return []
    if dtype != "route_deviation" or not isinstance(edf, (int, float)) or refund <= edf + 0.01:
        return []
    return [f"The refund S${refund:.2f} is more than the excess distance fare S${edf:.2f} "
            "(trip.fare_breakdown.excess_distance_fare). Policy v2.1 s1.3 refunds the excess distance "
            "fare only; tolls, time and surge are not part of it."]


def review(decision, context: dict) -> list[str]:
    """All problems with a draft ruling; empty when it may proceed to the Fairness audit."""
    return (check_facts(decision, context) + check_amount(decision, context) + check_photos(decision, context)
            + check_route_refund(decision, context))


def render_code_review(draft: dict, problems: list[str]) -> str:
    lines = ["\n=== CODE CHECK OF YOUR DRAFT RULING ===",
             "Your draft ruling: " + str(draft),
             "Code checked your draft against the platform records and found:"]
    lines += [f"- {p}" for p in problems]
    lines.append("Fix what is wrong. If the ruling really turns on a fact that is unverifiable or "
                 "contradicted, keep that status and set human_review_needed to true: a person will "
                 "decide. Do not mark a fact verified unless a record that nothing contradicts shows it.")
    return "\n".join(lines)
