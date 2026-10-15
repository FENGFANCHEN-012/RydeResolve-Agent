"""
Chat signals (D52): the tone of each chat message and the moments that matter in it.

Deterministic word lists, no LLM, so it costs nothing and gives the same answer every run.

Per message:
- tone: calm | frustrated | angry | abusive | distress
- events: agree, object, apology, promise (e.g. a rider agreeing to a detour)
Every label cites the message it came from (chat_log[i]).

What it is used for, and what it is never used for:
- Shown to the reviewer next to the case, and used to open a notice to an upset party
  with one acknowledging line. The ruling and the amount never change because of it.
- Not given to the advocates or the Judge: the chat itself already is, and "who is
  angrier" must not become evidence. Threats and abuse are the Safety agent's job
  (src/agents/safety.py); this module does not route any case.
- The Fairness audit uses the matching word list (DEMEANOUR_WORDS) the other way round:
  it flags a ruling whose reasons lean on a party's manner (see fairness.py, TONE_RELIANCE).

Chinese and Malay words are written as \\u escapes or ASCII so the file stays plain English.
"""
from __future__ import annotations

import re

CALM, FRUSTRATED, ANGRY, ABUSIVE, DISTRESS = "calm", "frustrated", "angry", "abusive", "distress"
# Higher = more serious; a party's overall tone is their most serious message
TONE_RANK = {CALM: 0, FRUSTRATED: 1, ANGRY: 2, ABUSIVE: 3, DISTRESS: 4}

_TONE_PATTERNS = {
    DISTRESS: [
        r"\b(i('m| am) (so )?(scared|afraid|frightened)|i feel unsafe|please stop the car|let me out|"
        r"emergency|somebody help|i('m| am) not safe)\b",
        "\u6551\u547d|\u5bb3\u6015|\u4e0d\u5b89\u5168",                       # save me / scared / unsafe
        r"\b(tolong|takut)\b",                    # Malay: help / afraid
    ],
    ABUSIVE: [
        r"\b(idiot|stupid|moron|bastard|f+u+c+k\w*|shit\w*|damn you|loser|useless (driver|rider|fellow)|"
        r"shut up|ki(a|o) ?si|knn|chee bye|lan ?jiao)\b",
        "\u7b28\u86cb|\u767d\u75f4|\u6eda",                           # idiot / idiot / get lost
        r"\b(bodoh|babi)\b",                      # Malay insults
    ],
    ANGRY: [
        r"\b(ridiculous|unacceptable|outrageous|scam(med)?|cheat(ed|ing)?|rip(ped)? ?off|how dare|"
        r"i('m| am) (so )?(angry|furious)|disgusting|never (use|ride|take) (ryde|this) again)\b",
        "\u9a97\u5b50|\u592a\u8fc7\u5206",                            # cheat / too much
    ],
    FRUSTRATED: [
        r"\b(still waiting|where are you|why (is|are|did|didn't|won't)|so (long|late)|been waiting|"
        r"not happy|annoy(ed|ing)|disappointed|wasted? (my )?time|hello\?+|seriously|wah lau|aiyo)\b",
        r"\?{2,}",
        "\u600e\u4e48\u8fd8|\u5230\u5e95",                            # why still / what on earth
    ],
}

_EVENT_PATTERNS = {
    # Starts with a yes-word, or names the other route; a question ("I go around ok?") is removed below
    "agree": [r"^\W*(ok(ay)?|sure|fine|yes|go ahead|no problem|agreed?)\b",
              r"\b(ok(ay)? fine|go ahead|take (that|the other|another) (route|way|road))\b", "\u53ef\u4ee5|\u597d\u7684|\u884c"],
    "object": [r"\b(no+,|don'?t (go|take|use)|not that way|wrong (way|route|road)|stop (here|the car)|"
               r"i didn'?t agree|why (are you|you) (going|taking)|i said no)\b", "\u4e0d\u8981|\u4e0d\u884c|\u8d70\u9519"],
    "apology": [r"\b(sorry|apologi[sz]e|my bad|my mistake|maaf)\b", "\u5bf9\u4e0d\u8d77|\u62b1\u6b49"],
    "promise": [r"\b(i('ll| will) (refund|pay|return|be there|come)|will refund|coming now|"
                r"(be there|arrive) in \d+)\b", "\u9a6c\u4e0a\u5230|\u4f1a\u9000"],
}

# Words about a party's manner rather than the facts; shared with the Fairness audit
DEMEANOUR_WORDS = re.compile(
    r"\b(rude(ness)?|impolite|attitude|aggressive(ly)?|hostile|angry|angrily|shout(ed|ing)?|"
    r"yell(ed|ing)?|sarcas(m|tic)|disrespect(ful)?|tone|demeanou?r|unfriendly|courteous|polite(ness)?)\b",
    re.I)


def _hits(patterns: list[str], text: str) -> bool:
    return any(re.search(p, text, flags=re.I) for p in patterns)


def message_signals(text: str) -> tuple[str, list[str]]:
    """(tone, events) for one message."""
    text = str(text or "")
    tone = next((t for t in (DISTRESS, ABUSIVE, ANGRY, FRUSTRATED) if _hits(_TONE_PATTERNS[t], text)), CALM)
    events = [e for e, pats in _EVENT_PATTERNS.items() if _hits(pats, text)]
    # An objection wins over agreement, and a question asks for agreement without giving it
    if "agree" in events and ("object" in events or text.rstrip().endswith("?")):
        events.remove("agree")
    return tone, events


def chat_signals(chat_log: list[dict] | None) -> dict:
    """Signals for a whole chat. Calls are skipped (no words to read)."""
    messages, overall = [], {}
    for i, m in enumerate(chat_log or []):
        if (m.get("message_type") or m.get("type")) == "call":
            continue
        text = m.get("message", m.get("content", ""))
        tone, events = message_signals(text)
        sender = m.get("sender") or "unknown"
        if tone != CALM or events:
            messages.append({"source": f"chat_log[{i}]", "sender": sender, "timestamp": m.get("timestamp"),
                             "tone": tone, "events": events, "text": str(text)[:200]})
        if TONE_RANK[tone] >= TONE_RANK.get(overall.get(sender, CALM), 0):
            overall[sender] = tone
    return {"messages": messages, "overall": overall,
            "note": "Tone is shown to reviewers and shapes notice wording only; it never changes a ruling."}


def party_tone(signals: dict | None, recipient: str) -> str:
    """Overall tone of a notice recipient ("passenger" or "driver"; the chat says "rider")."""
    sender = "rider" if recipient == "passenger" else recipient
    return ((signals or {}).get("overall") or {}).get(sender, CALM)
