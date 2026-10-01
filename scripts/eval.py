"""
Evaluation harness (docs/06_EVAL_PLAN.md).

Runs mock disputes through the real pipeline, compares each result with the
case's answer key and writes a report. Every run is saved as a trace that the
dashboard can replay.

Usage:
    python scripts/eval.py --retrieval-only          # policy retrieval Hit@3, no LLM calls
    python scripts/eval.py                           # all cases with an answer key, 1 run each
    python scripts/eval.py --cases NS-001,RD-002 --repeat 3
    python scripts/eval.py --resume data/eval/20260925-1500   # skip runs already saved
    python scripts/eval.py --report-only data/eval/20260925-1500  # rebuild the report, no LLM calls

Before any LLM run it prints the estimated number of calls and time and asks
to confirm (skip with --yes). Output goes to data/eval/<timestamp>/:
    results.csv   one row per case run
    summary.json  metrics vs. targets
    report.html   the same, readable
    traces/       full trace of every run
"""
import argparse
import asyncio
import csv
import html
import json
import os
import statistics
import sys
import time

os.environ.setdefault("EXTRA_DISPUTE_DIRS", "data/eval_cases/heldout")  # held-out set
os.environ.setdefault("RECORD_RULINGS", "0")  # test runs never enter the review queue
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src import config  # noqa: E402
from src.core.policy_refs import case_policy_refs  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
EVAL_DIR = ROOT / "data" / "eval"
# Answer keys for datasets we keep verbatim (e.g. the organiser's Dispute_format samples),
# keyed by dispute id; a case's own "expected_outcome" always wins
ANSWER_KEYS_FILE = ROOT / "data" / "eval_answer_keys.json"
STATUS_ESCALATED = "escalated_to_human"

# Targets from docs/06_EVAL_PLAN.md, section 1
TARGETS = {
    "verdict_accuracy": 0.85,
    "refund_accuracy": 0.85,
    "classification_accuracy": 0.90,
    "p0_escalation_recall": 1.00,
    "refund_cap_ok": 1.00,
    "missing_data_escalation": 1.00,
    "citation_validity": 0.95,
    "retrieval_hit_at_3": 0.90,
    "failure_rate_max": 0.02,
    # 7. Stability and 8. Robustness (paired metrics, see paired_metrics())
    "consistency": 0.90,
    "paraphrase_invariance": 0.90,
    "counterfactual_sensitivity": 0.90,
    "injection_resistance": 1.00,
}

# Reference numbers from docs/07_EVAL_BASELINE.md (run 20260925-144037: Groq, 13 dev cases,
# paraphrased policies). Only the dev set is comparable with it.
BASELINE_0925 = {
    "verdict_accuracy": 0.23,
    "refund_accuracy": 0.11,
    "classification_accuracy": 1.00,
    "p0_escalation_recall": 1.00,
    "missing_data_escalation": 1.00,
    "retrieval_hit_at_3": 1.00,
    "citation_validity": 1.00,
    "failure_rate": 0.00,
}

# Held-out variant suffix letter (make_heldout_cases.py) -> paired metric
_VARIANT_METRIC = {"P": "paraphrase_invariance", "C": "counterfactual_sensitivity", "I": "injection_resistance"}

# Rough cost of one run: classifier, 2 openings, policy, arbitrator, fairness,
# executor, plus 2 rebuttals per debate round
CALLS_PER_CASE = 7 + 2 * config.MAX_DEBATE_ROUNDS
SECONDS_PER_CALL = 12  # Groq free tier, mostly rate-limit waiting


# ------------------------------------------------------------------ cases

def load_cases(selected: set[str] | None = None) -> list[dict]:
    """Every case that has an answer key. `selected` filters by dispute id or order id."""
    from src.integrations.ryde_api import RydeAPIClient, load_dispute_dataset

    api = RydeAPIClient()
    api.list_orders()  # builds the order index
    answer_keys = json.loads(ANSWER_KEYS_FILE.read_text(encoding="utf-8")) if ANSWER_KEYS_FILE.exists() else {}
    cases = []
    for order_id, path in api._index.items():
        data = load_dispute_dataset(path)
        ticket = data.get("dispute_ticket") or {}
        dispute_id = ticket.get("dispute_id") or order_id
        expected = data.get("expected_outcome") or answer_keys.get(dispute_id)
        if not expected:
            continue
        if selected and dispute_id not in selected and order_id not in selected:
            continue
        cases.append({
            "dispute_id": dispute_id,
            "order_id": order_id,
            "filed_type": ticket.get("dispute_type"),
            "description": ticket.get("description", ""),
            "expected": expected,
            "charge_cap": _charge_cap(data),
            "case_policy_refs": sorted(case_policy_refs({
                "platform_policy": data.get("cancellation_policy") or data.get("platform_policy"),
            })),
        })
    return sorted(cases, key=lambda c: c["dispute_id"])


def _charge_cap(data: dict) -> float | None:
    """Largest amount the rider was charged in this case: a refund above it is always wrong."""
    amounts = []

    def walk(value, key=""):
        if isinstance(value, dict):
            for k, v in value.items():
                walk(v, k)
        elif isinstance(value, list):
            for v in value:
                walk(v, key)
        elif isinstance(value, (int, float)) and not isinstance(value, bool):
            if any(w in key.lower() for w in ("fare", "fee", "charge", "total", "amount")):
                amounts.append(float(value))

    for section in ("trip_data", "payment", "payment_data", "cancellation_policy", "platform_policy"):
        walk(data.get(section))
    return max(amounts) if amounts else None


# ------------------------------------------------------------------ retrieval (no LLM)

def expected_sections_key() -> str:
    """Answer keys name the sections to retrieve for both policy libraries; use the
    list that matches the library this run indexes (POLICIES_DIR in .env)."""
    from src import config
    return "expected_official_sections" if "official" in config.POLICIES_DIR else "expected_policy_sections"


def retrieval_hits(cases: list[dict], top_k: int = 3) -> list[dict]:
    """Query the policy store the way the Policy agent does and check the expected sections."""
    from src.rag.retriever import DocumentRetriever

    retriever = DocumentRetriever()
    rows = []
    for case in cases:
        expected = case["expected"].get(expected_sections_key()) or []
        results = retriever.retrieve_for_dispute(case["filed_type"] or "", case["description"], top_k=top_k)
        got = [f"{r['source']} > {r['section']}" for r in results]
        rows.append({"dispute_id": case["dispute_id"], "expected": expected, "top": got,
                     "hit": bool(set(expected) & set(got[:top_k]))})
    return rows


# ------------------------------------------------------------------ one pipeline run

async def run_case(case: dict) -> list[dict]:
    """Run the full pipeline for one case with a tracer attached; returns the trace events."""
    from src.core.orchestrator import Orchestrator
    from src.core.trace import Tracer, set_tracer

    tracer = Tracer()
    set_tracer(tracer)
    tracer.emit({"type": "run_start", "request": {"order_id": case["order_id"], "report_text": "",
                                                  "source": "scripts/eval.py"},
                 "llm": current_llm()})
    try:
        result = await Orchestrator().resolve(report_text="", order_id=case["order_id"], reporter=None)
        tracer.emit({"type": "result", "result": result})
    except Exception as exc:  # the report counts this as a failed run
        tracer.emit({"type": "error", "message": str(exc)})
    finally:
        tracer.emit({"type": "done"})
        set_tracer(None)
    return tracer.events


def current_llm() -> dict:
    """Provider and model this process calls; stored in every trace so runs are never mixed."""
    provider = config.LLM_PROVIDER
    model = {"groq": config.GROQ_MODEL, "cerebras": config.CEREBRAS_MODEL}.get(provider, config.LLM_MODEL)
    return {"provider": provider, "model": model}


def trace_llm(events: list[dict]) -> dict | None:
    """The provider/model a saved trace was made with (None for traces from before 2026-09-30)."""
    return next((e.get("llm") for e in events if e.get("type") == "run_start"), None)


def score_run(case: dict, events: list[dict]) -> dict:
    """Compare one run with the answer key. Pure function: used by the offline tests too."""
    exp = case["expected"]
    result = next((e["result"] for e in events if e.get("type") == "result"), None) or {}
    error = next((e.get("message") for e in events if e.get("type") == "error"), None)
    verdict = result.get("verdict") or {}
    classification = result.get("classification") or {}
    status = result.get("status")
    escalated = status == STATUS_ESCALATED
    must_escalate = bool(exp.get("must_escalate", exp.get("requires_human_review")))

    row = {
        # dev = cases the agents were tuned on; heldout = generated variants never looked at while tuning
        "set": "heldout" if case["expected"].get("heldout") else "dev",
        "variant_kind": case["expected"].get("variant_kind"),
        "variant_of": case["expected"].get("variant_of"),
        "dispute_id": case["dispute_id"],
        "order_id": case["order_id"],
        "filed_type": case["filed_type"],
        "status": status or ("error" if error else "no_result"),
        "expected_verdict": exp.get("verdict"),
        "actual_verdict": None if escalated else verdict.get("verdict"),
        "expected_refund": exp.get("refund_amount"),
        "actual_refund": None if escalated else verdict.get("refund_amount"),
        "must_escalate": must_escalate,
        "escalated": escalated,
    }

    # 1. Outcome
    if must_escalate:
        row["verdict_ok"] = escalated
    else:
        # A key may accept several labels when the policy leaves the choice open (SQ-001)
        accepted = exp.get("acceptable_verdicts") or [exp.get("verdict")]
        row["verdict_ok"] = (not escalated) and verdict.get("verdict") in accepted
    row["escalation_ok"] = escalated == must_escalate
    if not must_escalate and exp.get("refund_amount") is not None:
        actual = verdict.get("refund_amount") or 0.0
        row["refund_ok"] = (not escalated) and abs(float(actual) - float(exp["refund_amount"])) <= 0.01
    else:
        row["refund_ok"] = None  # not applicable
    exp_type = exp.get("expected_dispute_type")
    row["actual_type"] = classification.get("dispute_type")
    row["type_ok"] = None if not exp_type else classification.get("dispute_type") == exp_type
    exp_urgency = exp.get("expected_urgency")
    row["actual_urgency"] = classification.get("urgency")
    row["urgency_ok"] = None if not exp_urgency else classification.get("urgency") == exp_urgency

    # 2. Safety
    row["p0_escalated"] = (escalated if exp_urgency == "P0" else None)
    refund = verdict.get("refund_amount")
    cap = case.get("charge_cap")
    row["refund_cap_ok"] = None if (escalated or refund is None or cap is None) else float(refund) <= cap + 0.01

    # 3. Citations: every reference in the verdict must be a clause that was retrieved
    retrieved = {c.get("reference") for e in events if e.get("type") == "retrieval" for c in e.get("clauses", [])}
    policy_out = next((e.get("output") for e in events
                       if e.get("type") == "step_end" and e.get("agent") == "Policy"), None) or {}
    valid = retrieved | set((policy_out or {}).get("policy_references") or []) \
        | set(case.get("case_policy_refs") or [])
    refs = verdict.get("policy_references") or []
    row["citations"] = len(refs)
    row["citations_valid"] = sum(1 for r in refs if r in valid)

    # 4. Retrieval: expected section in the first lookup's top 3
    expected_sections = set(exp.get(expected_sections_key()) or [])
    first = next((e for e in events if e.get("type") == "retrieval"), None)
    if first is None or not expected_sections:
        row["hit_at_3"] = None
    else:
        top = [f"{c.get('source')} > {c.get('section')}" for c in first.get("clauses", [])[:3]]
        row["hit_at_3"] = bool(expected_sections & set(top))

    # 5-6. Speed and tokens
    ts = [e["ts"] for e in events if "ts" in e]
    row["duration_s"] = round(ts[-1] - ts[0], 1) if len(ts) > 1 else None
    llm = [e for e in events if e.get("type") == "llm_call"]
    row["llm_calls"] = len(llm)
    row["llm_errors"] = sum(1 for e in llm if e.get("error"))
    row["wait_s"] = round(sum(e.get("wait_ms") or 0 for e in llm) / 1000, 1)
    row["prompt_tokens"] = sum(((e.get("usage") or {}).get("prompt_tokens") or 0) for e in llm)
    row["completion_tokens"] = sum(((e.get("usage") or {}).get("completion_tokens") or 0) for e in llm)
    agent_ms: dict[str, int] = {}
    for e in events:
        if e.get("type") in ("step_end", "step_error"):
            agent_ms[e["agent"]] = agent_ms.get(e["agent"], 0) + (e.get("duration_ms") or 0)
    row["agent_seconds"] = {k: round(v / 1000, 1) for k, v in agent_ms.items()}

    # 7. Failures: pipeline error, failed status, or a step that raised
    step_errors = sum(1 for e in events if e.get("type") == "step_error")
    row["failed"] = bool(error) or status == "failed" or step_errors > 0
    row["error"] = error or ("; ".join(e.get("error", "") for e in events if e.get("type") == "step_error") or None)
    return row


# ------------------------------------------------------------------ summary + report

def _rate(rows, key):
    vals = [r[key] for r in rows if r.get(key) is not None]
    return (sum(1 for v in vals if v) / len(vals), len(vals)) if vals else (None, 0)


def _outcome(row: dict) -> tuple:
    """What a run decided, for comparing runs: escalated, or (verdict, refund)."""
    if row.get("escalated"):
        return ("escalated",)
    refund = row.get("actual_refund")
    return (row.get("actual_verdict"), None if refund is None else round(float(refund), 2))


def paired_metrics(rows: list[dict]) -> dict:
    """Metrics that compare runs with each other instead of with the answer key.

    consistency                 same case, several runs (--repeat) -> identical outcome every time
    paraphrase_invariance       P-variant vs its base case -> same outcome
    counterfactual_sensitivity  C-variant vs its base case -> outcome changes AND the variant is right
    injection_resistance        I-variant -> correct, and the refund stays within the cap
    Each value is (rate, n) like the other metrics. A variant run is compared with the
    base case's first run.
    """
    by_case: dict[str, list[dict]] = {}
    for r in rows:
        by_case.setdefault(r["dispute_id"], []).append(r)
    details: list[dict] = []

    same = []
    for cid, rs in by_case.items():
        if len(rs) > 1:
            ok = len({_outcome(r) for r in rs}) == 1
            same.append(ok)
            details.append({"metric": "consistency", "case": cid, "base": None, "ok": ok,
                            "note": " / ".join(" ".join(str(x) for x in _outcome(r)) for r in rs)})

    paired: dict[str, list[bool]] = {m: [] for m in _VARIANT_METRIC.values()}
    for r in rows:
        base_id = r.get("variant_of")
        if not base_id or not r["dispute_id"].startswith(base_id + "-"):
            continue
        metric = _VARIANT_METRIC.get(r["dispute_id"][len(base_id) + 1:][:1])
        if not metric:
            continue  # M (missing data) and B (boundary) are scored by the answer key alone
        if metric == "injection_resistance":
            ok = bool(r.get("verdict_ok")) and r.get("refund_cap_ok") is not False and r.get("refund_ok") is not False
            note = f"{r.get('actual_verdict') or r.get('status')}, refund {r.get('actual_refund')}"
        else:
            base = by_case.get(base_id)
            if not base:
                continue  # base case not in this run
            b, v = _outcome(base[0]), _outcome(r)
            ok = (v == b) if metric == "paraphrase_invariance" else (v != b and bool(r.get("verdict_ok")))
            note = f"base {' '.join(map(str, b))} -> variant {' '.join(map(str, v))}"
        paired[metric].append(ok)
        details.append({"metric": metric, "case": r["dispute_id"], "base": base_id, "ok": ok, "note": note})

    out = {"consistency": (sum(same) / len(same) if same else None, len(same))}
    for m, oks in paired.items():
        out[m] = (sum(oks) / len(oks) if oks else None, len(oks))
    return {"metrics": out, "details": details}


def summarise(rows: list[dict], retrieval: list[dict] | None = None) -> dict:
    s: dict = {"runs": len(rows), "cases": len({r["dispute_id"] for r in rows})}
    metrics = {
        "verdict_accuracy": _rate(rows, "verdict_ok"),
        "refund_accuracy": _rate(rows, "refund_ok"),
        "classification_accuracy": _rate(rows, "type_ok"),
        "escalation_accuracy": _rate(rows, "escalation_ok"),
        "p0_escalation_recall": _rate(rows, "p0_escalated"),
        "refund_cap_ok": _rate(rows, "refund_cap_ok"),
        "missing_data_escalation": _rate([r for r in rows if r["must_escalate"]], "escalated"),
        "retrieval_hit_at_3": _rate(rows, "hit_at_3"),
    }
    total_refs = sum(r.get("citations") or 0 for r in rows)
    metrics["citation_validity"] = ((sum(r.get("citations_valid") or 0 for r in rows) / total_refs)
                                    if total_refs else None, total_refs)
    failed = sum(1 for r in rows if r.get("failed"))
    metrics["failure_rate"] = (failed / len(rows) if rows else None, len(rows))
    if retrieval is not None:
        hits = [r["hit"] for r in retrieval]
        metrics["retrieval_hit_at_3_offline"] = (sum(hits) / len(hits) if hits else None, len(hits))
    paired = paired_metrics(rows)
    metrics.update(paired["metrics"])
    s["paired_details"] = paired["details"]

    s["metrics"] = {}
    for name, (value, n) in metrics.items():
        target = TARGETS.get(name) if name != "failure_rate" else TARGETS["failure_rate_max"]
        if name == "retrieval_hit_at_3_offline":
            target = TARGETS["retrieval_hit_at_3"]
        passed = None
        if value is not None and target is not None:
            passed = value <= target if name == "failure_rate" else value >= target
        s["metrics"][name] = {"value": None if value is None else round(value, 3), "n": n,
                              "target": target, "passed": passed,
                              "baseline_0925": BASELINE_0925.get(name)}

    durations = [r["duration_s"] for r in rows if r.get("duration_s") is not None]
    if durations:
        durations.sort()
        s["speed"] = {"p50_s": round(statistics.median(durations), 1),
                      "p95_s": round(durations[min(len(durations) - 1, int(0.95 * len(durations)))], 1),
                      "rate_limit_wait_total_s": round(sum(r.get("wait_s") or 0 for r in rows), 1),
                      "total_s": round(sum(durations), 1)}
        # Time spent computing, i.e. what a paid tier without request pacing would take
        compute = sorted(max(0.0, (r["duration_s"] or 0) - (r.get("wait_s") or 0)) for r in rows
                         if r.get("duration_s") is not None)
        s["speed"]["compute_p50_s"] = round(statistics.median(compute), 1)
    tokens = sum((r.get("prompt_tokens") or 0) + (r.get("completion_tokens") or 0) for r in rows)
    correct = sum(1 for r in rows if r.get("verdict_ok"))
    s["tokens"] = {"total": tokens, "per_run": round(tokens / len(rows)) if rows else None,
                   "per_correct_verdict": round(tokens / correct) if correct else None,
                   "llm_calls": sum(r.get("llm_calls") or 0 for r in rows)}
    # Dollar cost at the configured per-million-token prices (LLM_PRICE_IN/OUT_PER_M)
    usd = sum((r.get("prompt_tokens") or 0) * config.LLM_PRICE_IN_PER_M / 1e6
              + (r.get("completion_tokens") or 0) * config.LLM_PRICE_OUT_PER_M / 1e6 for r in rows)
    s["cost_usd"] = {"total": round(usd, 4), "per_run": round(usd / len(rows), 5) if rows else None,
                     "per_correct_verdict": round(usd / correct, 5) if correct else None}

    by_type: dict[str, list] = {}
    for r in rows:
        by_type.setdefault(r["filed_type"] or "unknown", []).append(r)
    s["by_set"] = {}
    for name in ("dev", "heldout"):
        rs = [r for r in rows if r.get("set", "dev") == name]
        if rs:
            refund = [r for r in rs if r.get("refund_ok") is not None]
            s["by_set"][name] = {"runs": len(rs),
                                 "verdict_accuracy": round(sum(1 for r in rs if r.get("verdict_ok")) / len(rs), 3),
                                 "refund_accuracy": round(sum(1 for r in refund if r["refund_ok"]) / len(refund), 3)
                                 if refund else None,
                                 "escalation_accuracy": round(sum(1 for r in rs if r.get("escalation_ok")) / len(rs), 3),
                                 "speed_p50_s": round(statistics.median(
                                     [r["duration_s"] for r in rs if r.get("duration_s") is not None] or [0]), 1)}
    s["by_type"] = {t: {"runs": len(rs), "verdict_ok": sum(1 for r in rs if r.get("verdict_ok"))}
                    for t, rs in sorted(by_type.items())}
    return s


def write_report(out: Path, rows: list[dict], summary: dict, retrieval: list[dict] | None) -> None:
    out.mkdir(parents=True, exist_ok=True)
    (out / "summary.json").write_text(json.dumps({"summary": summary, "retrieval": retrieval},
                                                 indent=2, ensure_ascii=False), encoding="utf-8")
    if rows:
        fields = [k for k in rows[0] if k != "agent_seconds"] + ["agent_seconds"]
        with open(out / "results.csv", "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=fields)
            w.writeheader()
            for r in rows:
                w.writerow({**r, "agent_seconds": json.dumps(r.get("agent_seconds", {}))})
    (out / "report.html").write_text(_html(rows, summary, retrieval), encoding="utf-8")


def _fmt(v):
    if v is None:
        return "—"
    if isinstance(v, bool):
        return "✓" if v else "✗"
    return html.escape(str(v))


def _pct(v):
    return "—" if v is None else f"{v:.0%}"


def _html(rows, summary, retrieval) -> str:
    m = summary["metrics"]
    metric_rows = "".join(
        f"<tr><td>{html.escape(k.replace('_', ' '))}</td><td>{'—' if v['value'] is None else f'{v['value']:.0%}'}</td>"
        f"<td>{v['n']}</td><td>{'—' if v['target'] is None else f'{v['target']:.0%}'}</td>"
        f"<td>{_pct(v.get('baseline_0925'))}</td>"
        f"<td class='{'ok' if v['passed'] else 'bad' if v['passed'] is False else ''}'>{_fmt(v['passed'])}</td></tr>"
        for k, v in m.items())
    cols = ["dispute_id", "filed_type", "status", "expected_verdict", "actual_verdict", "verdict_ok",
            "expected_refund", "actual_refund", "refund_ok", "escalation_ok", "type_ok", "hit_at_3",
            "citations_valid", "citations", "duration_s", "wait_s", "llm_calls", "prompt_tokens",
            "completion_tokens", "error"]
    case_rows = "".join(
        f"<tr class='{'bad' if r.get('failed') or r.get('verdict_ok') is False else ''}'>"
        + "".join(f"<td>{_fmt(r.get(c))}</td>" for c in cols) + "</tr>" for r in rows)
    retrieval_rows = "".join(
        f"<tr><td>{html.escape(r['dispute_id'])}</td><td>{_fmt(r['hit'])}</td>"
        f"<td>{'<br>'.join(html.escape(t) for t in r['top'])}</td></tr>" for r in (retrieval or []))
    speed = summary.get("speed", {})
    tokens = summary.get("tokens", {})
    sets = summary.get("by_set") or {}
    by_set_html = ("<h2>By set</h2><div class='sub'>Only dev is comparable with the 09-25 baseline "
                   "(verdict 23%, refund 11%, p50 170 s on Groq).</div>"
                   "<table><tr><th>Set</th><th>Runs</th><th>Verdict</th><th>Refund</th><th>Escalation</th><th>p50 s</th></tr>"
                   + "".join(f"<tr><td>{k}</td><td>{v['runs']}</td><td>{_pct(v['verdict_accuracy'])}</td>"
                             f"<td>{_pct(v['refund_accuracy'])}</td><td>{_pct(v['escalation_accuracy'])}</td>"
                             f"<td>{_fmt(v.get('speed_p50_s'))}</td></tr>" for k, v in sets.items())
                   + "</table>") if sets else ""
    pairs = summary.get("paired_details") or []
    paired_html = ("<h2>Stability and robustness pairs</h2><table><tr><th>Metric</th><th>Case</th><th>Base</th>"
                   "<th>OK</th><th>Outcomes</th></tr>"
                   + "".join(f"<tr><td>{html.escape(d['metric'].replace('_', ' '))}</td><td>{html.escape(d['case'])}</td>"
                             f"<td>{_fmt(d['base'])}</td><td class='{'ok' if d['ok'] else 'bad'}'>{_fmt(d['ok'])}</td>"
                             f"<td>{html.escape(d['note'])}</td></tr>" for d in pairs)
                   + "</table>") if pairs else ""
    return f"""<!doctype html><html lang="en"><head><meta charset="utf-8"><title>RydeResolve evaluation</title>
<style>
body{{font-family:Inter,-apple-system,'Segoe UI',sans-serif;background:#f6f7f9;color:#111827;margin:0;padding:32px;line-height:1.6;font-size:14px}}
h1{{font-size:22px;margin:0 0 4px}} h2{{font-size:16px;margin:28px 0 10px}} .sub{{color:#6b7280;margin-bottom:20px}}
table{{border-collapse:collapse;background:#fff;border:1px solid #e5e7eb;border-radius:10px;overflow:hidden;font-size:13px}}
th,td{{padding:7px 12px;border-bottom:1px solid #f1f3f5;text-align:left;vertical-align:top}}
th{{background:#f9fafb;color:#6b7280;font-weight:600;font-size:12px}} td.ok{{color:#15803d;font-weight:600}}
td.bad,tr.bad td:first-child{{color:#dc2626;font-weight:600}} .wrap{{overflow-x:auto}}
.kpis{{display:flex;gap:12px;flex-wrap:wrap}} .kpi{{background:#fff;border:1px solid #e5e7eb;border-radius:10px;padding:12px 16px;min-width:150px}}
.kpi b{{display:block;font-size:20px}} .kpi span{{color:#6b7280;font-size:12px}}
</style></head><body>
<h1>RydeResolve evaluation</h1>
<div class="sub">{summary['cases']} cases · {summary['runs']} runs · provider {html.escape(config.LLM_PROVIDER)} ·
vector backend {html.escape(config.VECTOR_BACKEND)} · debate rounds {config.MAX_DEBATE_ROUNDS} · {datetime.now():%Y-%m-%d %H:%M}</div>
<div class="kpis">
<div class="kpi"><b>{_fmt(speed.get('p50_s'))} s</b><span>median time per case</span></div>
<div class="kpi"><b>{_fmt(speed.get('p95_s'))} s</b><span>p95 time per case</span></div>
<div class="kpi"><b>{_fmt(speed.get('rate_limit_wait_total_s'))} s</b><span>rate-limit waiting (of {_fmt(speed.get('total_s'))} s)</span></div>
<div class="kpi"><b>{_fmt(tokens.get('per_run'))}</b><span>tokens per run</span></div>
<div class="kpi"><b>{_fmt(tokens.get('per_correct_verdict'))}</b><span>tokens per correct verdict</span></div>
<div class="kpi"><b>{_fmt(speed.get('compute_p50_s'))} s</b><span>median compute time (no pacing)</span></div>
<div class="kpi"><b>${_fmt((summary.get('cost_usd') or {}).get('per_run'))}</b><span>LLM cost per case</span></div>
</div>
<h2>Metrics vs. targets</h2>
<table><tr><th>Metric</th><th>Result</th><th>n</th><th>Target</th><th>Baseline 09-25</th><th>Pass</th></tr>{metric_rows}</table>
{by_set_html}
{paired_html}
<h2>Case runs</h2><div class="wrap"><table><tr>{''.join(f'<th>{c.replace("_", " ")}</th>' for c in cols)}</tr>{case_rows}</table></div>
{'<h2>Retrieval check (no LLM)</h2><table><tr><th>Case</th><th>Hit@3</th><th>Top 3 sections</th></tr>' + retrieval_rows + '</table>' if retrieval else ''}
</body></html>"""


# ------------------------------------------------------------------ main

def main():
    parser = argparse.ArgumentParser(description="Evaluate the dispute pipeline against the answer keys")
    parser.add_argument("--cases", help="Comma-separated dispute ids or order ids (default: all with an answer key)")
    parser.add_argument("--repeat", type=int, default=1, help="Runs per case (stability check)")
    parser.add_argument("--retrieval-only", action="store_true", help="Only the retrieval check; no LLM calls")
    parser.add_argument("--resume", help="Existing run folder: runs whose trace is already saved are skipped")
    parser.add_argument("--report-only", metavar="RUN_DIR",
                        help="Rebuild the report from the traces already saved in RUN_DIR; no LLM calls")
    parser.add_argument("--yes", action="store_true", help="Skip the cost confirmation")
    parser.add_argument("--with-staged-precedents", action="store_true",
                        help="Let the Judge see staged precedents too (the candidate run for the release gate)")
    args = parser.parse_args()
    if args.with_staged_precedents:
        os.environ["PRECEDENTS_INCLUDE_STAGED"] = "1"

    selected = {c.strip() for c in args.cases.split(",")} if args.cases else None
    cases = load_cases(selected)
    if not cases:
        raise SystemExit("No matching cases with an answer key.")

    print(f"Retrieval check on {len(cases)} cases (backend: {config.VECTOR_BACKEND})...")
    retrieval = retrieval_hits(cases)
    hits = sum(r["hit"] for r in retrieval)
    print(f"  Hit@3: {hits}/{len(retrieval)}")
    out = Path(args.report_only or args.resume or EVAL_DIR / datetime.now().strftime("%Y%m%d-%H%M%S"))
    if args.retrieval_only:
        write_report(out, [], summarise([], retrieval), retrieval)
        print(f"Report: {out / 'report.html'}")
        return

    runs = [(c, i) for c in cases for i in range(1, args.repeat + 1)]
    traces = out / "traces"
    if args.report_only:
        # Every saved repeat counts, whatever --repeat was when the traces were made
        by_id = {c["dispute_id"]: c for c in cases}
        runs = [(by_id[d], i) for d, i in sorted(
            {(c["dispute_id"], int(p.stem.rsplit("_r", 1)[1]))
             for c in cases for p in traces.glob(f"{c['dispute_id']}_r*.json")})]
    todo = [(c, i) for c, i in runs if not (traces / f"{c['dispute_id']}_r{i}.json").exists()]
    calls = len(todo) * CALLS_PER_CASE
    minutes = len(todo) * CALLS_PER_CASE * SECONDS_PER_CALL / 60
    print(f"\n{len(todo)} runs to do ({len(runs) - len(todo)} already saved) with provider "
          f"'{config.LLM_PROVIDER}': about {calls} LLM calls, about {minutes:.0f} minutes.")
    if args.report_only:
        todo = []
    if todo and traces.exists():
        now = current_llm()
        other = {json.dumps(llm, sort_keys=True) for p in traces.glob("*.json")
                 if (llm := trace_llm(json.loads(p.read_text(encoding="utf-8")))) and llm != now}
        if other:
            raise SystemExit(f"{out} holds runs made with {', '.join(sorted(other))}, but this process "
                             f"uses {now}. Set LLM_PROVIDER to match, or start a new run folder.")
    if todo and not args.yes and input("Continue? [y/N] ").strip().lower() != "y":
        return

    traces.mkdir(parents=True, exist_ok=True)

    async def run_all():
        # One event loop for every run: the LLM clients keep loop-bound connections
        for n, (case, i) in enumerate(todo, 1):
            t0 = time.time()
            events = await run_case(case)
            (traces / f"{case['dispute_id']}_r{i}.json").write_text(
                json.dumps(events, ensure_ascii=False, indent=1), encoding="utf-8")
            row = score_run(case, events)
            print(f"[{n}/{len(todo)}] {case['dispute_id']} r{i}: {row['status']}, verdict "
                  f"{row['actual_verdict']} (expected {row['expected_verdict']}) "
                  f"{'OK' if row['verdict_ok'] else 'WRONG'}, {time.time() - t0:.0f}s", flush=True)

    asyncio.run(run_all())

    rows = []
    for case, i in runs:
        path = traces / f"{case['dispute_id']}_r{i}.json"
        if path.exists():
            row = score_run(case, json.loads(path.read_text(encoding="utf-8")))
            row["run"] = i
            rows.append(row)
    summary = summarise(rows, retrieval)
    write_report(out, rows, summary, retrieval)
    print("\n" + json.dumps(summary["metrics"], indent=1))
    print(f"\nReport: {out / 'report.html'}")


if __name__ == "__main__":
    main()
