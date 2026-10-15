"""Replay the Clerk (src/agents/clerk.py) over the saved rulings of an eval run, no pipeline run.

Usage: python scripts/clerk_replay.py data/eval/<run> [KEY_ENV_NAME]
Reads each trace's Collector context, retrieved clauses and FINAL Arbitrator decision; asks the
Clerk about every rule the rationale relied on; writes <run>_clerk.json and prints a summary.
What to look for: every wrong ruling that cited a misread rule should get a "misapplied"; no
correct ruling should.
"""
from __future__ import annotations

import ast
import asyncio
import csv
import glob
import json
import os
import sys
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def _load_key(name: str) -> str:
    for line in (ROOT / ".env").read_text(encoding="utf-8").splitlines():
        if line.startswith(name + "="):
            return line.split("=", 1)[1].strip().strip('"')
    raise SystemExit(f"{name} not in .env")


def _obj(v):
    if isinstance(v, str):
        try:
            return json.loads(v)
        except Exception:
            return ast.literal_eval(v)
    return v


def _parts(trace: list) -> tuple[dict, list, dict | None]:
    context, clauses, decision = {}, [], None
    for e in trace:
        if e.get("type") == "step_end" and e.get("agent") == "Collector":
            context = _obj(e["output"])
        elif e.get("type") == "retrieval":
            clauses = _obj(e["clauses"])
        elif e.get("type") == "step_end" and e.get("agent") == "Arbitrator":
            decision = _obj(e["output"])      # the last one is the final ruling
    return context, clauses, decision


async def main() -> None:
    run = Path(sys.argv[1])
    key_name = sys.argv[2] if len(sys.argv) > 2 else "CEREBRAS_API_KEY_3"
    os.environ["CEREBRAS_API_KEY"] = _load_key(key_name)
    os.environ["LLM_PROVIDER"] = "cerebras"
    from src.agents.clerk import ClerkAgent, problems
    from src.core.llm_client import LLMClient

    results_csv = {(r["dispute_id"], r.get("run", "1")): r
                   for r in csv.DictReader(open(run / "results.csv", encoding="utf-8"))}
    clerk = ClerkAgent(LLMClient(provider="cerebras", fallbacks=[]))
    out_path = Path(str(run) + "_clerk.json")
    done = json.loads(out_path.read_text(encoding="utf-8")) if out_path.exists() else {}

    for f in sorted(glob.glob(str(run / "traces" / "*.json"))):
        name = Path(f).stem
        if name in done:
            continue
        cid, rnum = name.rsplit("_r", 1)
        context, clauses, decision = _parts(json.load(open(f, encoding="utf-8")))
        if not decision or not decision.get("verdict"):
            done[name] = {"skipped": "no ruling (escalated before the Judge)"}
            continue
        d = SimpleNamespace(**decision)
        res = await clerk.check(d, context, clauses)
        r = results_csv.get((cid, rnum), {})
        done[name] = {"verdict": decision.get("verdict"), "expected": r.get("expected_verdict"),
                      "verdict_ok": r.get("verdict_ok"), "status": r.get("status"),
                      "checks": res, "problems": problems(res)}
        out_path.write_text(json.dumps(done, indent=1, ensure_ascii=False), encoding="utf-8")
        flag = "MISAPPLIED" if done[name]["problems"] else "ok"
        print(f"{name}: ruling={decision.get('verdict')} ok={r.get('verdict_ok')} -> {flag} "
              f"({sum(1 for x in res if 'skipped' not in x)} checked)", flush=True)
        for p in done[name]["problems"]:
            print("    !", p[:220], flush=True)

    print("\n=== summary")
    flagged = [(n, v) for n, v in done.items() if v.get("problems")]
    print(f"rulings checked: {sum(1 for v in done.values() if 'checks' in v)}, flagged: {len(flagged)}")
    for n, v in flagged:
        print(f"  {n}: ruling {v['verdict']} (expected {v['expected']}, ok={v['verdict_ok']})")


if __name__ == "__main__":
    asyncio.run(main())
