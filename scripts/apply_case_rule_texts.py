"""Write the scope text of every case policy key into the case files (D36).

Each key in a case's cancellation_policy / platform_policy becomes {"value": ..., "text": ...},
with the text taken from data/policies/case_rule_texts.json. Values are never changed.
Idempotent: a key already in the new format gets its text refreshed from the glossary.

    python scripts/apply_case_rule_texts.py            # dry run: counts and missing keys
    python scripts/apply_case_rule_texts.py --write    # rewrite the files

Only key names are ever printed, so it is safe to run over the sealed sets.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
GLOSSARY = ROOT / "data" / "policies" / "case_rule_texts.json"
CASE_DIRS = ["data/mock_disputes", "data/eval_cases/heldout", "data/eval_cases/stress_new",
             "data/eval_cases/fraud", "data/eval_cases/sealed", "data/eval_cases/sealed_a",
             "data/eval_cases/sealed_b", "data/eval_cases/samples_qwen"]
SECTIONS = ("cancellation_policy", "platform_policy")


def wrap_block(block: dict, texts: dict, missing: set) -> dict:
    out = {}
    for k, v in block.items():
        value = v["value"] if isinstance(v, dict) and set(v) <= {"value", "text"} and "value" in v else v
        if k.startswith("_") or k not in texts:
            if not k.startswith("_"):
                missing.add(k)
            out[k] = v
            continue
        out[k] = {"value": value, "text": texts[k]}
    return out


def _block_span(raw: str, section: str) -> tuple[int, int, int] | None:
    """(start, end, indent) of the {...} object after "<section>": in the raw text, so only
    that block is rewritten and the rest of the file keeps its exact formatting."""
    key = f'"{section}"'
    i = raw.find(key)
    if i < 0:
        return None
    start = raw.find("{", i + len(key))
    if start < 0 or raw[i + len(key):start].strip() != ":":
        return None
    depth, in_str, esc = 0, False, False
    for j in range(start, len(raw)):
        c = raw[j]
        if in_str:
            esc = (c == "\\" and not esc)
            if c == '"' and not esc:
                in_str = False
            elif c != "\\":
                esc = False
            continue
        if c == '"':
            in_str = True
        elif c == "{":
            depth += 1
        elif c == "}":
            depth -= 1
            if depth == 0:
                line_start = raw.rfind("\n", 0, i) + 1
                return start, j + 1, i - line_start
    return None


def rewrite(raw: str, data: dict) -> str:
    nl = "\r\n" if "\r\n" in raw else "\n"
    for s in SECTIONS:
        if not isinstance(data.get(s), dict):
            continue
        span = _block_span(raw, s)
        if span is None:
            raise ValueError(f"cannot locate {s}")
        start, end, indent = span
        body = json.dumps(data[s], indent=2, ensure_ascii=False).replace("\n", nl + " " * indent)
        raw = raw[:start] + body + raw[end:]
    return raw


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--write", action="store_true")
    args = ap.parse_args()
    texts = {k: v for k, v in json.loads(GLOSSARY.read_text(encoding="utf-8")).items()
             if not k.startswith("_")}
    missing: set[str] = set()
    changed = files = 0
    for d in CASE_DIRS:
        for path in sorted((ROOT / d).glob("*.json")):
            raw = path.read_bytes().decode("utf-8")
            data = json.loads(raw)
            if not any(isinstance(data.get(s), dict) for s in SECTIONS):
                continue
            files += 1
            for s in SECTIONS:
                if isinstance(data.get(s), dict):
                    data[s] = wrap_block(data[s], texts, missing)
            new = rewrite(raw, data)
            if json.loads(new) != data:
                raise ValueError(f"rewrite check failed: {path.name}")
            if new != raw:
                changed += 1
                if args.write:
                    path.write_bytes(new.encode("utf-8"))
    print(f"{files} case files with a policy block, {changed} {'rewritten' if args.write else 'would change'}")
    if missing:
        print("keys with no text in the glossary:", ", ".join(sorted(missing)))
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
