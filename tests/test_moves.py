"""D24 step 3: typed debate moves and the issue summary for the Judge."""
import json

from src.core.moves import has_open_challenge, issue_summary, parse_moves, render_issue_summary, render_moves


def reply(*moves):
    return json.dumps({"moves": list(moves)})


def test_parse_keeps_valid_moves_and_rejects_prose():
    raw = "```json\n" + reply({"type": "challenge", "target": "D2", "text": "No.", "cites": ["E3"]},
                              {"type": "shout", "text": "x"}) + "\n```"
    assert parse_moves(raw) == [{"type": "challenge", "target": "D2", "text": "No.", "cites": ["E3"]}]
    assert parse_moves("The driver is wrong because ...") is None
    assert "CHALLENGE D2: No. (cites E3)" in render_moves(parse_moves(raw))


def test_issue_summary_agreed_and_contested():
    history = [
        {"id": "D1", "speaker": "passenger", "round": 0, "content": {}},
        {"id": "D4", "speaker": "passenger", "round": 1, "moves": parse_moves(reply(
            {"type": "challenge", "target": "E2", "text": "GPS shows 1.1 km away.", "cites": ["E2"]},
            {"type": "challenge", "target": "D2", "text": "No arrival event.", "cites": ["E1"]}))},
        {"id": "D5", "speaker": "driver", "round": 1, "moves": parse_moves(reply(
            {"type": "concede", "target": "E2", "text": "The car was 1.1 km away at 18:01.", "cites": ["E2"]}))},
    ]
    s = issue_summary(history)
    assert [a["target"] for a in s["agreed"]] == ["E2"]
    assert [(c["target"], c["answered"]) for c in s["contested"]] == [("D2", False)]
    text = render_issue_summary(s)
    assert "driver conceded E2" in text and "challenged D2 [D4] (not answered)" in text
    assert has_open_challenge(history[:2]) and not has_open_challenge(history)
