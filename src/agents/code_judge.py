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
problems; if the second draft still fails, the case goes to a person (human_review_needed).
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


def check_facts(decision, context: dict) -> list[str]:
    facts = [f for f in (getattr(decision, "decisive_facts", None) or []) if isinstance(f, dict)]
    if not facts:
        return ["The ruling lists no decisive facts: name the facts it turns on, their records and "
                "whether each is verified."]
    flagged: dict[str, str] = {}
    for f in _findings(context):
        if f.get("kind") in ("conflict", "gap"):
            for src in f.get("sources") or []:
                flagged.setdefault(str(src), f"{f.get('kind')}: {f.get('statement')}")
    problems = []
    for f in facts:
        status = str(f.get("status") or "").lower()
        name = str(f.get("fact") or "?")[:160]
        if status not in FACT_STATUSES:
            problems.append(f"Decisive fact \"{name}\" has no valid status (verified / unverifiable / contradicted).")
            continue
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


def review(decision, context: dict) -> list[str]:
    """All problems with a draft ruling; empty when it may proceed to the Fairness audit."""
    return check_facts(decision, context) + check_amount(decision, context)


def render_code_review(draft: dict, problems: list[str]) -> str:
    lines = ["\n=== CODE CHECK OF YOUR DRAFT RULING ===",
             "Your draft ruling: " + str(draft),
             "Code checked your draft against the platform records and found:"]
    lines += [f"- {p}" for p in problems]
    lines.append("Fix what is wrong. If the ruling really turns on a fact that is unverifiable or "
                 "contradicted, keep that status and set human_review_needed to true: a person will "
                 "decide. Do not mark a fact verified unless a record that nothing contradicts shows it.")
    return "\n".join(lines)
