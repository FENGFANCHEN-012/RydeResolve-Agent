"""
Triage: how much process a case gets (D24, ported to main without evidence pools).

Two labels, both from code signals already in the case (no LLM call, same answer every run,
every label carries its reasons):
- complexity: "simple" | "complex"
- risk:       "safe"   | "dangerous"

What the labels change:
- simple: one debate round.
- complex: up to COMPLEX_MAX_ROUNDS rounds; a further round runs only when a side says its
  last rebuttal raised a new point (NEW_POINT tag, see src/core/debate.py). Otherwise the
  sides would repeat themselves: on main the advocates cannot find new evidence mid-debate.
- simple + safe: Fairness runs its code checks only, no LLM audit. Every other case gets
  the full audit. The code checks always run (they caught the NS-002 fee errors).
- dangerous: always the full audit; the Safety agent has already picked a tier.

A label can only be raised by a signal, never lowered: no input can make a case with a data
conflict "simple", or a case with a threat "safe".
"""
from __future__ import annotations

import os

from src.agents.case_brief import disputed_charge
from src.agents.fraud import LOW as FRAUD_LOW

COMPLEX_MAX_ROUNDS = int(os.getenv("COMPLEX_MAX_ROUNDS", "2"))
# A disputed amount above this (SGD) is enough on its own to make a case complex
COMPLEX_AMOUNT_SGD = float(os.getenv("COMPLEX_AMOUNT_SGD", "30"))
# This many data gaps (missing records) make a case complex
COMPLEX_MIN_GAPS = 2


def triage(context, classification=None, fraud_report: dict | None = None) -> dict:
    brief = getattr(context, "case_brief", None) or {}
    report = fraud_report or {}
    urgency = getattr(getattr(classification, "urgency", None), "value",
                      getattr(classification, "urgency", None))

    complex_reasons: list[str] = []
    conflicts = brief.get("conflicts") or []
    if conflicts:
        complex_reasons.append(f"{len(conflicts)} data conflict(s) between sources")
    gaps = brief.get("gaps") or []
    if len(gaps) >= COMPLEX_MIN_GAPS:
        complex_reasons.append(f"{len(gaps)} data gaps")
    if report.get("level") and report.get("level") != FRAUD_LOW:
        complex_reasons.append(f"fraud risk {report['level']}")
    amount = disputed_charge(context)
    if amount is not None and amount > COMPLEX_AMOUNT_SGD:
        complex_reasons.append(f"disputed amount S${amount:.2f} > S${COMPLEX_AMOUNT_SGD:.0f}")

    danger_reasons: list[str] = []
    if urgency == "P0":
        danger_reasons.append("P0 safety report")
    if report.get("safety_alerts"):
        danger_reasons.append(f"{len(report['safety_alerts'])} safety alert(s) in the chat")

    return _grade(complex_reasons, danger_reasons)


def _grade(complex_reasons: list[str], danger_reasons: list[str]) -> dict:
    complexity = "complex" if complex_reasons else "simple"
    risk = "dangerous" if danger_reasons else "safe"
    return {
        "complexity": complexity,
        "risk": risk,
        "max_rounds": COMPLEX_MAX_ROUNDS if complexity == "complex" else 1,
        "fairness_llm_audit": not (complexity == "simple" and risk == "safe"),
        "reasons": complex_reasons + danger_reasons or ["no complexity or risk signal"],
    }
