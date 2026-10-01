"""Shared helpers for the retrieval comparison: load the test set and the official
sections, and decide whether a retrieved chunk is relevant to a question.

A chunk is relevant when it comes from a gold file and either names a gold
section heading or shares most of its text with a gold section. The text test
lets both systems be scored the same way even when a chunk has no heading
(e.g. the second half of a long section)."""
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OFFICIAL = ROOT / "data" / "policies" / "official"
EVAL_SET = Path(__file__).with_name("eval_set.json")
NGRAM = 6


def load_questions() -> list[dict]:
    return json.loads(EVAL_SET.read_text(encoding="utf-8"))["questions"]


def words(text: str) -> list[str]:
    # Letters/digits only, so curly quotes, mojibake and markdown do not break matches
    return re.findall(r"[a-z0-9]+", text.lower())


def ngrams(text: str) -> set[tuple]:
    w = words(text)
    return {tuple(w[i:i + NGRAM]) for i in range(len(w) - NGRAM + 1)}


def load_sections() -> dict[str, list[tuple[str, str]]]:
    """file stem -> [(heading, section text)] for every "## " section."""
    out = {}
    for f in sorted(OFFICIAL.glob("*.md")):
        if f.name == "README.md":
            continue
        parts = re.split(r"\n(?=## )", f.read_text(encoding="utf-8"))
        out[f.stem] = [(p.split("\n", 1)[0].lstrip("# ").strip(), p) for p in parts]
    return out


SECTIONS = load_sections()
_GOLD_GRAMS: dict[tuple, set] = {}


def _gold_grams(stem: str, heading_part: str) -> set:
    key = (stem, heading_part)
    if key not in _GOLD_GRAMS:
        grams = set()
        for heading, text in SECTIONS.get(stem, []):
            if heading_part.lower() in heading.lower():
                grams |= ngrams(text)
        _GOLD_GRAMS[key] = grams
    return _GOLD_GRAMS[key]


def is_relevant(stem: str, heading: str, text: str, gold: list[list[str]]) -> bool:
    """Relevant if the chunk is from a gold file and (a) one of its "## " headings
    names a gold section, (b) most of the chunk is gold-section text, or (c) the
    chunk contains most of a gold section (ADP merges short sections into one chunk)."""
    chunk = ngrams(text)
    headings = [heading] + re.findall(r"^## (.+)$", text, re.M)
    for g_stem, g_head in gold:
        if stem != g_stem:
            continue
        if any(h and g_head.lower() in h.lower() for h in headings):
            return True
        g = _gold_grams(g_stem, g_head)
        if chunk and g and (len(chunk & g) / len(chunk) >= 0.5 or len(chunk & g) / len(g) >= 0.5):
            return True
    return False


def score(ranked_relevance: list[bool]) -> dict:
    """Hit@1/3/8 and reciprocal rank for one question's ranked results."""
    first = next((i + 1 for i, r in enumerate(ranked_relevance) if r), None)
    return {
        "hit1": first == 1,
        "hit3": first is not None and first <= 3,
        "hit8": first is not None and first <= 8,
        "rr": 1 / first if first else 0.0,
        "first_rank": first,
    }


def summarise(rows: list[dict]) -> dict:
    n = len(rows)
    agg = {k: round(sum(r[k] for r in rows) / n, 3) for k in ("hit1", "hit3", "hit8", "rr")}
    agg["mrr"] = agg.pop("rr")
    agg["n"] = n
    return agg
