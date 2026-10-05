"""
Seed the riders and drivers table from the dataset profiles (mock_disputes + eval cases).

Only the people are imported: their platform history (trips, rating, prior complaints,
prior fraud flags) becomes the prior_* columns. The cases themselves and their expected
outcomes are NOT imported, so no answer key ever reaches the history an agent reads.
The sealed set is never read. People already in the store are left untouched.

    python scripts/seed_people.py            # dry run against STORE_URL / DATABASE_URL
    python scripts/seed_people.py --apply
"""
import argparse
import glob
import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from src import config  # noqa: E402  (loads .env)
from src.store.db import Store  # noqa: E402
from src.store.people import DRIVER, RIDER, Driver, Rider, person_from_profile  # noqa: E402

# Base cases first, so a person who also appears in a variant keeps the base profile
SOURCES = ["mock_disputes", "eval_cases/heldout", "eval_cases/fraud"]


def load_profiles() -> dict[tuple[str, str], tuple[dict, str | None, str]]:
    found = {}
    for folder in SOURCES:
        for path in sorted(glob.glob(os.path.join(config.DATA_DIR, folder, "*.json"))):
            with open(path, encoding="utf-8") as f:
                case = json.load(f)
            as_of = (case.get("dispute_ticket") or {}).get("filed_at")
            for role, key in ((RIDER, "rider_profile"), (DRIVER, "driver_profile")):
                profile = case.get(key)
                if isinstance(profile, dict) and profile.get(f"{role}_id"):
                    found.setdefault((role, profile[f"{role}_id"]), (profile, as_of, f"{folder}/{os.path.basename(path)}"))
    return found


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true", help="write (default: dry run)")
    ap.add_argument("--to", help="target STORE_URL (default: STORE_URL / DATABASE_URL / local sqlite)")
    args = ap.parse_args()

    store = Store(args.to)
    profiles = load_profiles()
    with store.session() as s:
        new = [(role, pid, *v) for (role, pid), v in profiles.items()
               if s.get(Rider if role == RIDER else Driver, pid) is None]
        print(f"profiles found: {len(profiles)} ({sum(r == RIDER for r, _ in profiles)} riders, "
              f"{sum(r == DRIVER for r, _ in profiles)} drivers); new to the store: {len(new)}")
        if not args.apply:
            print("dry run; add --apply to write")
            return 0
        for role, pid, profile, as_of, _src in new:
            s.add(person_from_profile(role, profile, as_of, source="seed"))
        s.commit()
    print(f"seeded {len(new)} people")
    return 0


if __name__ == "__main__":
    sys.exit(main())
