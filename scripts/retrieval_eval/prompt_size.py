"""Prompt size per agent for every eval case, offline (no LLM). Builds the same context and
case brief the pipeline would, then the user prompts the agents send. Analyses fed to the
Judge are the ones recorded in a saved eval run, so its prompt is realistic. (D15)

    python scripts/retrieval_eval/prompt_size.py [eval run folder]
Tokens are estimated as characters / 4.
"""
import asyncio
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
os.environ.setdefault("EXTRA_DISPUTE_DIRS", "data/eval_cases/heldout")

from src.agents.arbitrator import ArbitrationAgent  # noqa: E402
from src.agents.case_brief import CaseBriefAgent  # noqa: E402
from src.agents.collector import CollectorAgent  # noqa: E402
from src.agents.driver import DriverAgent  # noqa: E402
from src.agents.passenger import PassengerAgent  # noqa: E402
from src.integrations.ryde_api import RydeAPIClient, load_dispute_dataset  # noqa: E402
from src.rag.retriever import DocumentRetriever  # noqa: E402

RUN = Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "data" / "eval" / "20261001-114026"


def recorded(run: Path, case: str) -> dict:
    """Round-0 analyses and debate history from a saved trace, keyed like the workflow."""
    path = run / "traces" / f"{case}_r1.json"
    if not path.exists():
        return {}
    out, history = {}, []
    for e in json.loads(path.read_text(encoding="utf-8")):
        if e.get("type") == "step_end" and e.get("agent") in ("Passenger", "Driver", "Policy"):
            history.append({"speaker": e["agent"].lower(), "content": e.get("output")})
            out.setdefault(e["agent"], e.get("output") or {})
    out["history"] = history
    return out


async def main():
    api = RydeAPIClient()
    api.list_orders()
    retriever = DocumentRetriever()
    brief_agent = CaseBriefAgent(retriever=retriever)
    totals, n = {"passenger": 0, "driver": 0, "judge": 0}, 0
    for order_id, path in sorted(api._index.items()):
        data = load_dispute_dataset(path)
        did = (data.get("dispute_ticket") or {}).get("dispute_id") or order_id
        ctx = await CollectorAgent().collect_from_dataset(path)
        ctx = ctx.model_copy(update={"case_brief": await brief_agent.build(ctx)})
        clauses = PassengerAgent._format_clauses(ctx.case_brief["clause_texts"])
        dtype = getattr(ctx.type, "value", ctx.type) or "unknown"
        rec = recorded(RUN, did)
        sizes = {
            "passenger": len(PassengerAgent._build_user_prompt(ctx, dtype, clauses)),
            "driver": len(DriverAgent._build_user_prompt(ctx, dtype, clauses)),
            "judge": len(ArbitrationAgent._build_user_prompt(
                ctx.model_dump(), rec.get("Passenger", {}), rec.get("Driver", {}),
                rec.get("Policy", {}), rec.get("history", []))),
        }
        for k, v in sizes.items():
            totals[k] += v
        n += 1
    print(f"{n} cases, average user-prompt size (tokens ~ chars/4):")
    for k, v in totals.items():
        print(f"  {k:<10} {v // n // 4:>6}")


if __name__ == "__main__":
    asyncio.run(main())
