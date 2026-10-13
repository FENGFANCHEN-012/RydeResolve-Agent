"""Load saved evaluation traces into the trace store, so the dashboard can replay them.

A live run depends on the LLM provider (quota, HTTP 429, a different ruling on a rerun). For a demo,
the moments worth showing are replayed from the run that produced them, under "Saved runs".

    python scripts/import_demo_traces.py data/eval/<run>/traces/RD-001_r1.json [...more traces]

Each trace is stored as "demo-<n>-<case>.json"; names sort above the timestamped live runs. The
case itself must be loadable by the server (data/mock_disputes, or a folder in EXTRA_DISPUTE_DIRS).
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.store.db import get_store  # noqa: E402


def main(paths: list[str]) -> None:
    store = get_store()
    existing = set(store.list_trace_names(500))
    for n, p in enumerate(paths, 1):
        events = json.loads(Path(p).read_text(encoding="utf-8"))
        start = next((e for e in events if e.get("type") == "run_start"), {})
        order_id = (start.get("request") or {}).get("order_id")
        name = f"demo-{n}-{Path(p).stem.split('_r')[0]}.json"
        if name in existing:
            print("already there:", name)
            continue
        store.save_trace(name, order_id, events)
        print("saved:", name, order_id)


if __name__ == "__main__":
    if len(sys.argv) < 2:
        sys.exit(__doc__)
    main(sys.argv[1:])
