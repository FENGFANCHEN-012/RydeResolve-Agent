"""Validate sealed case format."""
import json, re, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
POLICY_DIR = ROOT / "data" / "policies" / "official"
SEALED_DIR = ROOT / "data" / "eval_cases" / "sealed"

sections = set()
for p in sorted(POLICY_DIR.glob("ryde_*.md")):
    title = " ".join(w.capitalize() for w in p.stem.split("_"))
    text = p.read_text(encoding="utf-8")
    for h in re.findall(r"^## (.+)$", text, flags=re.M):
        sections.add(f"{title} > {h.strip()}")

TYPES = ["no_show", "cancellation_refund", "fare_dispute", "route_deviation",
         "service_quality", "cleaning_fee", "driver_rights"]

ok = 0
bad = 0
for f in sorted(SEALED_DIR.glob("SL-*.json")):
    case = json.loads(f.read_text(encoding="utf-8"))
    issues = []
    for key in ("dispute_ticket", "trip_data", "app_events", "expected_outcome"):
        if key not in case:
            issues.append(f"missing {key}")
    if issues:
        print(f"{f.name}: {'; '.join(issues)}")
        bad += 1
        continue
    t, e = case["dispute_ticket"], case["expected_outcome"]
    if t.get("trip_id") != case["trip_data"].get("trip_id"):
        issues.append("trip_id mismatch")
    if t.get("dispute_type") not in TYPES:
        issues.append(f"unknown type {t.get('dispute_type')}")
    if e.get("verdict") not in ("upheld", "partially_upheld", "dismissed", None):
        issues.append("bad verdict")
    if (e.get("verdict") is None) != bool(e.get("must_escalate")):
        issues.append("verdict/must_escalate mismatch")
    bad_secs = [s for s in e.get("expected_official_sections") or [] if s not in sections]
    if bad_secs:
        issues.append(f"{len(bad_secs)} bad section(s): {bad_secs[0][:50]}...")
    if not issues:
        print(f"{f.name} ({t.get('dispute_type')}): OK")
        ok += 1
    else:
        print(f"{f.name} ({t.get('dispute_type')}): {'; '.join(issues)}")
        bad += 1

print(f"\n{ok} OK, {bad} with issues")
sys.exit(0 if bad == 0 else 1)
