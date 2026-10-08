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


def test_step3b_done_flag_dedup_and_open_challenge_on_conceded_point():
    from src.core.moves import both_done, parse_done
    raw = reply({"type": "claim", "target": "", "text": "Nothing new.", "cites": ["E1"]})
    assert parse_done(raw.replace("]}", "], \"done\": true}")) and not parse_done(raw)
    concede = {"type": "concede", "target": "D2", "text": "Fare matches quote.", "cites": ["fare_check.quoted_vs_charged"]}
    history = [
        {"id": "D4", "speaker": "passenger", "round": 1, "moves": [concede], "done": True},
        {"id": "D5", "speaker": "driver", "round": 1, "done": True, "moves": [
            dict(concede, text="We also accept it."),
            {"type": "challenge", "target": "D2", "text": "Already agreed.", "cites": ["fare_check.quoted_vs_charged"]}]},
    ]
    s = issue_summary(history)
    assert len(s["agreed"]) == 1 and s["agreed"][0]["by"] == "passenger and driver"
    assert not has_open_challenge(history)       # the challenge is about a conceded point
    assert both_done(history, 1)


def test_step3b_same_records_are_one_item():
    from src.agents.collector_tools import Finding
    from src.core.evidence_pool import EvidencePool, EvidencePoolItem
    f = [Finding(id="e", tool="events_between", kind="fact", statement="s", sources=["app_events[6]"])]
    a = EvidencePoolItem.from_collector_tool("passenger", "events_between", {"start": "T1", "end": "T2"}, f)
    b = EvidencePoolItem.from_collector_tool("passenger", "events_between", {"start": "T1b", "end": "T2b"}, f)
    assert len(EvidencePool.merge_pools([], [a, b])) == 1
