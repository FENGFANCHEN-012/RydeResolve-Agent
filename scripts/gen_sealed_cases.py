"""Generate a sealed held-out eval set with Gemini (a different model family from the one that
wrote the code), so the generalisation number does not come from cases the developer wrote
knowing the fixes (D16, overfitting protocol).

Gemini gets only: the official policy text, the case format (one dev case as example) and the
labelling conventions. It is not told what the code does or what was fixed.

    $env:GEMINI_API_KEY = "..."      (or GEMINI_API_KEY in .env)
    python scripts/gen_sealed_cases.py --count 10

Writes data/eval_cases/sealed/SL-*.json. The sealed set is not in the default eval; run it once,
before submission:  $env:EXTRA_DISPUTE_DIRS="data/eval_cases/heldout;data/eval_cases/sealed"
This script prints ids and mechanical problems only, never the answer keys, so the developer
stays blind to them.
"""
import argparse
import json
import os
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
POLICY_DIR = ROOT / "data" / "policies" / "official"
EXAMPLE_CASE = ROOT / "data" / "mock_disputes" / "fare_dispute_01.json"
CONVENTIONS = ROOT / "data" / "mock_disputes" / "README.md"
OUT_DIR = ROOT / "data" / "eval_cases" / "sealed"
MODEL = os.environ.get("GEMINI_MODEL", "gemini-3.1-pro-preview")
CEREBRAS_URL = "https://api.cerebras.ai/v1/chat/completions"
BATCH = 5  # cases per call, keeps each response well under the output limit

TYPES = ["no_show", "cancellation_refund", "fare_dispute", "route_deviation",
         "service_quality", "cleaning_fee", "driver_rights"]


def source_title(path: Path) -> str:
    """ryde_help_rider_fares_and_charges.md -> Ryde Help Rider Fares And Charges (index naming)."""
    return " ".join(w.capitalize() for w in path.stem.split("_"))


def load_policies() -> tuple[str, set[str]]:
    """All official policy text, and the set of valid "<Source> > <Article>" section names."""
    parts, sections = [], set()
    for p in sorted(POLICY_DIR.glob("ryde_*.md")):
        title = source_title(p)
        text = p.read_text(encoding="utf-8")
        for h in re.findall(r"^## (.+)$", text, flags=re.M):
            sections.add(f"{title} > {h.strip()}")
        parts.append(f"=== SOURCE: {title} ===\n{text}")
    return "\n\n".join(parts), sections


def conventions() -> str:
    text = CONVENTIONS.read_text(encoding="utf-8")
    return text[text.index("## Labelling conventions"):]


PROMPT = """You are designing an independent TEST SET for an automated ride-hailing dispute
resolution system used by Ryde (Singapore). You do not know how the system works and must not
guess at it. Write realistic disputes and the answer a careful, fair human reviewer would give
under the policies below.

Write exactly {n} NEW dispute cases. Dispute types for this batch: {types}.
Across the set, vary the correct outcome: some upheld, some partially upheld, some dismissed, and
some where the right answer is to send the case to a human (evidence missing, contradictory or
insufficient to decide safely). Include cases where the person who filed is wrong. Make the
records realistic and internally consistent (timestamps, distances, fares, GPS points, chat).
Do not copy the example's situation.

Make the cases hard enough to test judgement, not rule lookup:
- At least one case in this batch must have conflicting evidence (e.g. a party's statement or
  chat contradicts the GPS / app events), or a party who misstates facts in their favour.
- At least one case in this batch should involve more than one issue (e.g. part of the request
  is justified and part is not, or a second problem surfaces in the records).
- The case's own policy block states rules and numbers only (fees, thresholds, what evidence a
  charge needs). It must NEVER name the outcome or the action to take (no keys or values such
  as "action", "human_review", "refund", "verdict", "escalate"). The reviewer must work it out.
- Give enough records to reason from: at least 8 GPS points for any trip that moved, at least
  5 chat messages where the parties talked, and a full app event timeline.
{avoid}
FORMAT: each case is a JSON object with the same top-level keys as the example
(dispute_ticket, rider_profile, driver_profile, trip_data, gps_telemetry, chat_logs, app_events,
and the applicable policy block: cancellation_policy for no-show / cancellation, platform_policy
otherwise), plus expected_outcome. Use dispute_id "{prefix}NN" and trip_id "{trip_prefix}NNN" with
the numbers given below. Amounts in SGD.

expected_outcome keys:
  heldout: true
  verdict: "upheld" | "partially_upheld" | "dismissed", or null when the case must go to a human
     (upheld = the filer gets everything they asked for, counting anything already done before
     the ruling; partially_upheld = only part; dismissed = nothing)
  acceptable_verdicts: list, only when the policy genuinely allows more than one label
  refund_amount: number (0.0 when nothing is refunded) or null when it must not be scored
  recommended_action: short snake_case string
  requires_human_review: boolean;  must_escalate: boolean (true when verdict is null)
  reason: the reviewer's reasoning, citing the evidence and the rule (say "this trip's policy"
     for a rule from the case's own policy block)
  expected_dispute_type: the dispute type
  expected_official_sections: list of "<SOURCE title> > <article heading>" strings, copied
     exactly from the SOURCE headers and "## " headings below, for the articles that decide it

Numbers for this batch: {numbers}

LABELLING CONVENTIONS (follow them):
{conventions}

EXAMPLE CASE (format only):
{example}

OFFICIAL RYDE POLICIES:
{policies}

Respond with a JSON array of {n} case objects and nothing else."""


def call_gemini(prompt: str) -> list[dict]:
    from google import genai
    from google.genai import types
    client = genai.Client(api_key=os.environ["GEMINI_API_KEY"])
    resp = client.models.generate_content(
        model=MODEL, contents=prompt,
        config=types.GenerateContentConfig(response_mime_type="application/json", temperature=0.9))
    cases = json.loads(resp.text)
    if not isinstance(cases, list):
        raise ValueError("Gemini did not return a JSON array")
    return cases


def call_cerebras(prompt: str, model: str, retry: bool = True) -> list[dict]:
    """Same prompt through Cerebras (OpenAI-compatible); JSON mode needs an object, so cases are wrapped."""
    import httpx
    key = os.environ.get("CEREBRAS_API_KEY_BACKUP") or os.environ["CEREBRAS_API_KEY"]
    body = {"model": model, "temperature": 0.9, "max_completion_tokens": 40000,
            "response_format": {"type": "json_object"},
            "messages": [{"role": "user", "content": prompt +
                          ' Wrap the array in an object: {"cases": [...]}.'}]}
    r = httpx.post(CEREBRAS_URL, json=body, headers={"Authorization": f"Bearer {key}"}, timeout=600)
    r.raise_for_status()
    data = r.json()
    u = data.get("usage") or {}
    print(f"  tokens: {u.get('prompt_tokens')} in / {u.get('completion_tokens')} out")
    try:
        cases = json.loads(data["choices"][0]["message"]["content"]).get("cases")
    except json.JSONDecodeError:
        if not retry:
            print("  invalid JSON again, batch skipped")
            return []
        print("  invalid JSON from the model, retrying once")
        return call_cerebras(prompt, model, retry=False)
    if not isinstance(cases, list):
        raise ValueError("model did not return a cases array")
    return cases


def problems(case: dict, sections: set[str]) -> list[str]:
    """Mechanical checks only (format, ids, cited sections); never judges the answer."""
    out = []
    for key in ("dispute_ticket", "trip_data", "app_events", "expected_outcome"):
        if key not in case:
            out.append(f"missing {key}")
    if out:
        return out
    t, e = case["dispute_ticket"], case["expected_outcome"]
    if t.get("trip_id") != case["trip_data"].get("trip_id"):
        out.append("trip_id differs between ticket and trip_data")
    if t.get("dispute_type") not in TYPES:
        out.append(f"unknown dispute_type {t.get('dispute_type')}")
    if e.get("verdict") not in ("upheld", "partially_upheld", "dismissed", None):
        out.append(f"bad verdict value")
    if (e.get("verdict") is None) != bool(e.get("must_escalate")):
        out.append("verdict null and must_escalate disagree")
    policy = json.dumps(case.get("cancellation_policy") or case.get("platform_policy") or {}).lower()
    if re.search(r"action|human_review|verdict|escalat|refund_due|uphold|dismiss", policy):
        out.append("case policy block names an outcome or action")
    bad = [s for s in e.get("expected_official_sections") or [] if s not in sections]
    if bad:
        out.append(f"{len(bad)} cited section(s) not in the policy index")
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--count", type=int, default=10)
    ap.add_argument("--prefix", default="SL-", help='case id prefix, e.g. "SA-"')
    ap.add_argument("--out", default=str(OUT_DIR), help="output folder")
    ap.add_argument("--provider", choices=["gemini", "cerebras"], default="gemini")
    ap.add_argument("--types", default=None, help="comma-separated dispute types to cycle (default: all)")
    ap.add_argument("--batch", type=int, default=BATCH, help="cases per call (use 3 for qwen)")
    ap.add_argument("--model", default=None, help="Cerebras model (default qwen-3.8-27b)")
    args = ap.parse_args()
    from dotenv import load_dotenv
    load_dotenv(ROOT / ".env")
    if args.provider == "gemini" and not os.environ.get("GEMINI_API_KEY"):
        print("GEMINI_API_KEY is not set (environment or .env).")
        return 1
    out_dir = Path(args.out)
    tag = args.prefix.rstrip("-")
    trip_prefix = f"RYDE-{tag}-" if args.prefix != "SL-" else "RYDE-SEAL-"
    generate = (call_gemini if args.provider == "gemini"
                else lambda pr: call_cerebras(pr, args.model or "qwen-3.8-27b"))

    policies, sections = load_policies()
    example = EXAMPLE_CASE.read_text(encoding="utf-8")
    out_dir.mkdir(parents=True, exist_ok=True)
    start = len(list(out_dir.glob(f"{args.prefix}*.json"))) + 1
    written, summaries = [], []
    for b in range(0, args.count, args.batch):
        n = min(args.batch, args.count - b)
        nums = list(range(start + b, start + b + n))
        pool = args.types.split(",") if args.types else TYPES
        types_ = [pool[(i - 1) % len(pool)] for i in nums]
        avoid = ("Already written (do not repeat these situations): " + "; ".join(summaries) + "\n"
                 if summaries else "")
        prompt = PROMPT.format(
            n=n, types=", ".join(types_), avoid=avoid, prefix=args.prefix, trip_prefix=trip_prefix,
            numbers=", ".join(f"{args.prefix}{i:02d} / {trip_prefix}{i:03d}" for i in nums),
            conventions=conventions(), example=example, policies=policies)
        for case in generate(prompt):
            cid = (case.get("dispute_ticket") or {}).get("dispute_id") or f"{args.prefix}{nums[0]:02d}-x"
            path = out_dir / f"{cid}.json"
            if path.exists():
                print(f"{cid}: already exists, skipped")
                continue
            path.write_text(json.dumps(case, indent=2, ensure_ascii=False), encoding="utf-8")
            written.append(cid)
            ticket = case.get("dispute_ticket") or {}
            summaries.append(f"{ticket.get('dispute_type')}: {str(ticket.get('description'))[:80]}")
            issues = problems(case, sections)
            print(f"{cid} ({ticket.get('dispute_type')}): " + ("OK" if not issues else "; ".join(issues)))
    print(f"\n{len(written)} cases written to {out_dir} (answer keys not shown).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
