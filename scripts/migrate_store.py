"""
Copy the local record store (and the old data/traces/*.json files) into another database,
e.g. Supabase Postgres. Rows keep their ids, so the audit hash chain stays valid.

    python scripts/migrate_store.py --to "postgresql://..."            # dry run: counts only
    python scripts/migrate_store.py --to "postgresql://..." --apply    # copy

Refuses to write into a target that already has rulings, reviews, precedents or audit
entries, so it can never mix two histories. Traces already in the target are skipped.
"""
import argparse
import glob
import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from sqlalchemy import func, select, text  # noqa: E402

from src import config  # noqa: E402
from src.store.db import DEFAULT_URL, AuditEntry, Precedent, Review, Ruling, Store, Trace  # noqa: E402

# Parents before children, so foreign keys hold while copying
TABLES = [Ruling, Review, Precedent, AuditEntry]


def row_dict(obj) -> dict:
    return {c.name: getattr(obj, c.name) for c in obj.__table__.columns}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--to", required=True, help="target STORE_URL")
    ap.add_argument("--from", dest="src", default=DEFAULT_URL, help="source STORE_URL (default: local sqlite)")
    ap.add_argument("--apply", action="store_true", help="actually write (default: dry run)")
    args = ap.parse_args()

    src, dst = Store(args.src), Store(args.to)  # creating the Store creates any missing tables
    trace_files = sorted(glob.glob(os.path.join(config.DATA_DIR, "traces", "*.json")))

    with src.session() as s, dst.session() as d:
        rows = {m: list(s.scalars(select(m).order_by(m.id))) for m in TABLES + [Trace]}
        busy = {m.__tablename__: d.scalar(select(func.count()).select_from(m)) for m in TABLES}
        have_traces = set(d.scalars(select(Trace.name)))

        for m in TABLES + [Trace]:
            print(f"{m.__tablename__:12} source rows: {len(rows[m])}")
        new_files = [f for f in trace_files if os.path.basename(f) not in have_traces]
        print(f"trace files  in data/traces: {len(trace_files)} ({len(new_files)} not yet in target)")

        if any(busy.values()):
            print(f"REFUSED: target already has data {busy}")
            return 1
        ok, bad = src.verify_audit_chain()
        if not ok:
            print(f"REFUSED: source audit chain is broken at entry {bad}")
            return 1
        if not args.apply:
            print("dry run; add --apply to copy")
            return 0

        for m in TABLES:
            for obj in rows[m]:
                d.add(m(**row_dict(obj)))
            d.flush()
        for obj in rows[Trace]:
            if obj.name not in have_traces:
                d.add(Trace(**{k: v for k, v in row_dict(obj).items() if k != "id"}))
                have_traces.add(obj.name)
        for f in new_files:
            name = os.path.basename(f)
            if name in have_traces:
                continue
            with open(f, encoding="utf-8") as fh:
                events = json.load(fh)
            order_id = name.split("_", 1)[1][:-5] if "_" in name else None
            d.add(Trace(name=name, order_id=order_id, events=events))
        d.flush()

        if dst.is_postgres:
            # Explicit ids leave the id sequences behind; move them past the copied rows
            for m in TABLES + [Trace]:
                t = m.__tablename__
                d.execute(text(f"SELECT setval(pg_get_serial_sequence('{t}', 'id'), "
                               f"COALESCE((SELECT MAX(id) FROM {t}), 0) + 1, false)"))
        d.commit()

    ok, bad = dst.verify_audit_chain()
    print(f"copied; target audit chain {'intact' if ok else f'BROKEN at {bad}'}")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
