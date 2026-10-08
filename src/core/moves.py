"""
Typed debate moves (D24 step 3).

A rebuttal is a list of moves instead of free prose:
- claim:     a point the speaker puts forward
- challenge: disputes a specific turn [D#], evidence item [E#] or fact id; the other side must
             answer it on its next turn
- concede:   accepts a specific turn, item or fact as true (an advocate that concedes a fact
             can still argue about what it means)

After the debate the system lists what both sides accept and what is still contested, so the
Judge rules on the open issues instead of re-reading every turn. Parsing is forgiving: a reply
that is not valid JSON is kept as plain text, so a model slip never loses an argument.
"""
from __future__ import annotations

import json
import re

MOVE_TYPES = ("claim", "challenge", "concede")
_MAX_MOVES = 6
_MAX_TEXT = 400
_REF = re.compile(r"\b(?:D\d+|E\d+)\b|\[[^\]]+\]")

MOVES_INSTRUCTION = (
    "Answer as JSON only, no prose outside it:\n"
    '{"moves": [{"type": "claim" | "challenge" | "concede", "target": "<D#, E# or fact id; '
    'required for challenge and concede>", "text": "<one or two sentences>", '
    '"cites": ["<ids you rely on: fact ids, E#, policy refs, D#>"]}], "done": true | false}\n'
    "- claim: a point for your side. challenge: dispute a specific turn, item or fact of the other "
    "side (they must answer it). concede: accept something true even if it hurts you; conceding "
    "honestly is better than denying a recorded fact. You may concede FACTS, never the OUTCOME: do "
    "not argue for the other side's result (that is the Judge's call). Never concede your own turns.\n"
    "- done: true when you have no new point for your side (nothing new found, nothing left to "
    "answer); then give at most one claim stating your remaining position.\n"
    f"- At most {_MAX_MOVES} moves, about 180 words in total. Every move cites at least one id; a "
    "move with no id carries no weight. Answer the other side's open challenges first. If the "
    "other side found new evidence, address it."
)


def parse_moves(raw) -> list[dict] | None:
    """The moves in a rebuttal reply, or None when the reply is not a moves object."""
    text = str(raw or "").strip()
    if text.startswith("```"):
        text = text.strip("`").split("\n", 1)[-1]
    start, end = text.find("{"), text.rfind("}")
    if start < 0 or end <= start:
        return None
    try:
        data = json.loads(text[start:end + 1])
    except json.JSONDecodeError:
        return None
    moves = []
    for m in (data.get("moves") if isinstance(data, dict) else None) or []:
        if not isinstance(m, dict) or m.get("type") not in MOVE_TYPES:
            continue
        cites = [str(c) for c in m.get("cites") or [] if str(c).strip()][:8]
        moves.append({"type": m["type"], "target": str(m.get("target") or "").strip()[:40],
                      "text": " ".join(str(m.get("text") or "").split())[:_MAX_TEXT], "cites": cites})
    return moves[:_MAX_MOVES] or None


def parse_done(raw) -> bool:
    """The advocate's "done" flag: nothing new to add for its side."""
    text = str(raw or "")
    start, end = text.find("{"), text.rfind("}")
    try:
        data = json.loads(text[start:end + 1]) if 0 <= start < end else {}
    except json.JSONDecodeError:
        return False
    return bool(isinstance(data, dict) and data.get("done") is True)


def render_moves(moves: list[dict]) -> str:
    """Moves as the text other agents read, e.g. 'CHALLENGE D4: ... (cites E3)'."""
    lines = []
    for m in moves:
        head = m["type"].upper() + (f" {m['target']}" if m.get("target") else "")
        lines.append(f"{head}: {m['text']}" + (f" (cites {', '.join(m['cites'])})" if m.get("cites") else ""))
    return "\n".join(lines)


def issue_summary(history: list[dict]) -> dict:
    """What both sides accept and what is still contested after the debate.
    agreed: every concession (who accepted what). contested: every challenge, marked answered
    when the challenged side made any later move about the same target or turn."""
    agreed, contested = [], []
    agreed_at: dict[tuple, dict] = {}   # one line per conceded fact, however often it was conceded
    turns = [h for h in history if h.get("moves")]
    for i, turn in enumerate(turns):
        for m in turn["moves"]:
            if m["type"] == "concede":
                key = tuple(sorted(m.get("cites") or [])) or (m["target"],)
                if key in agreed_at:
                    if turn["speaker"] not in agreed_at[key]["by"]:
                        agreed_at[key]["by"] += f" and {turn['speaker']}"
                    continue
                agreed_at[key] = {"by": turn["speaker"], "turn": turn.get("id"), "target": m["target"],
                                  "text": m["text"]}
                agreed.append(agreed_at[key])
            elif m["type"] == "challenge":
                later = [t for t in turns[i + 1:] if t["speaker"] != turn["speaker"]]
                answered = any(mv.get("target") in (m["target"], turn.get("id")) or
                               turn.get("id") in mv.get("cites", []) for t in later for mv in t["moves"])
                conceded = any(mv["type"] == "concede" and mv.get("target") == m["target"]
                               for t in later for mv in t["moves"])
                if not conceded:
                    contested.append({"by": turn["speaker"], "turn": turn.get("id"), "target": m["target"],
                                      "text": m["text"], "answered": answered})
    return {"agreed": agreed, "contested": contested}


def render_issue_summary(summary: dict) -> str:
    if not summary.get("agreed") and not summary.get("contested"):
        return ""
    lines = ["=== ISSUES AFTER THE DEBATE (built from the typed moves) ==="]
    if summary.get("agreed"):
        lines.append("Accepted by the side it hurts (treat as common ground unless the records contradict it):")
        lines.extend(f"- {a['by']} conceded {a['target']} [{a['turn']}]: {a['text']}" for a in summary["agreed"])
    if summary.get("contested"):
        lines.append("Still contested (rule on these):")
        lines.extend(f"- {c['by']} challenged {c['target']} [{c['turn']}]"
                     + ("" if c["answered"] else " (not answered)") + f": {c['text']}"
                     for c in summary["contested"])
    lines.append("=== END OF ISSUES ===")
    return "\n".join(lines)


def has_open_challenge(history: list[dict]) -> bool:
    """True when the last turn challenges something the other side has not already conceded.
    A challenge against a point already accepted as common ground needs no further round
    (D24 step 3b: FD-002 ran a whole second round that only repeated the concessions)."""
    if not history:
        return False
    conceded = {m["target"] for h in history for m in h.get("moves") or [] if m["type"] == "concede"}
    conceded |= {c for h in history for m in h.get("moves") or [] if m["type"] == "concede"
                 for c in m.get("cites") or []}
    return any(m["type"] == "challenge" and m["target"] not in conceded
               and not set(m.get("cites") or []) <= conceded
               for m in history[-1].get("moves") or [])


def both_done(history: list[dict], round_num: int) -> bool:
    """Both advocates said they have nothing new in this round."""
    turns = [h for h in history if h.get("round") == round_num and h.get("speaker") in ("passenger", "driver")]
    return len(turns) == 2 and all(h.get("done") for h in turns)
