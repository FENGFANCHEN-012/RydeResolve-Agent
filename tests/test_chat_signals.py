"""Chat tone and key moments (D52): labels, notice wording, and the Fairness tone check."""
import pytest
from fastapi.testclient import TestClient

from src.agents.arbitrator import Decision, Verdict
from src.agents.chat_signals import chat_signals, message_signals, party_tone
from src.agents.executor import ExecutionAgent
from src.agents.fairness import FairnessAgent, FairnessIssueCode, FairnessRecommendation
from tests.test_fairness_agent import FakeLLMClient, make_context, make_decision, make_input


@pytest.mark.parametrize("text,tone,events", [
    ("ok fine, take the other way", "calm", ["agree"]),
    ("No, don't go that way", "calm", ["object"]),
    ("Boss, road ahead got problem, I go around ok?", "calm", []),   # a question asks, it does not agree
    ("I'm at the bus stop now", "calm", []),                         # "stop" alone is not an objection
    ("Still waiting, where are you??", "frustrated", []),
    ("This is a scam, unacceptable", "angry", []),
    ("you idiot", "abusive", []),
    ("I feel unsafe, please stop the car", "distress", ["object"]),
    ("Sorry, traffic jam, be there in 5", "calm", ["apology", "promise"]),
    ("可以", "calm", ["agree"]),
    ("Why you never reply? I know where you stay already haha", "abusive", []),   # SI-001: a threat
    ("Can I have your number for the receipt?", "calm", []),
])
def test_message_labels(text, tone, events):
    assert message_signals(text) == (tone, events)


def test_chat_signals_cite_the_message_and_skip_calls():
    chat = [{"sender": "rider", "message": "hello", "message_type": "message"},
            {"sender": "driver", "message": "", "message_type": "call"},
            {"sender": "rider", "content": "Still waiting??", "type": "message"}]
    sig = chat_signals(chat)
    assert [m["source"] for m in sig["messages"]] == ["chat_log[2]"]
    assert party_tone(sig, "passenger") == "frustrated" and party_tone(sig, "driver") == "calm"


def _notes(signals):
    result = {"notifications": []}
    decision = Decision(verdict=Verdict.PARTIALLY_UPHELD, confidence=0.9, rationale="r", refund_amount=3.44)
    ExecutionAgent()._generate_notifications(decision=decision, dispute_id="D1", language="en", result=result,
                                             escalated=False, reporter="passenger", chat_signals=signals)
    return {n["recipient"]: n["message"] for n in result["notifications"]}


def test_tone_changes_the_opening_line_only():
    calm = _notes(None)
    upset = _notes(chat_signals([{"sender": "rider", "message": "This is a scam!"}]))
    assert upset["passenger"].startswith("We understand this trip was frustrating")
    assert upset["passenger"].endswith(calm["passenger"])     # same outcome, same amount
    assert upset["driver"] == calm["driver"]                  # the calm party gets the plain notice


@pytest.mark.asyncio
async def test_fairness_flags_reasons_that_rest_on_manner_without_blocking():
    rude = make_decision(rationale=make_decision().rationale + " The driver was also rude to the rider.")
    a = await FairnessAgent(llm_client=FakeLLMClient()).assess(make_input(decision=rude))
    note = next(i for i in a.issues if i.code == FairnessIssueCode.TONE_RELIANCE)
    assert note.severity == "medium" and "rude" in note.description
    assert a.recommendation != FairnessRecommendation.BLOCK
    # a conduct complaint is about manner: no flag there
    conduct = make_input(decision=rude, context=make_context(type="service_quality"))
    b = await FairnessAgent(llm_client=FakeLLMClient()).assess(conduct)
    assert FairnessIssueCode.TONE_RELIANCE not in {i.code for i in b.issues}


def test_chat_signals_endpoint():
    from src.api import main
    client = TestClient(main.app, headers={"Authorization": "Bearer offline-demo"})
    r = client.post("/api/chat-signals", json={"chat_log": [{"sender": "rider", "content": "ok go ahead"}]})
    assert r.status_code == 200 and r.json()["messages"][0]["events"] == ["agree"]


class _FakeLLM:
    def __init__(self, reply):
        self.reply, self.calls = reply, []

    async def chat_json(self, messages, **kw):
        self.calls.append(messages)
        if isinstance(self.reply, Exception):
            raise self.reply
        return self.reply


CHAT = [{"sender": "rider", "content": "Still waiting??"},
        {"sender": "rider", "content": "Great, just great. Thanks for the scenic tour."},
        {"sender": "driver", "content": "Kenapa lama sangat?"}]


@pytest.mark.asyncio
async def test_model_relabels_only_the_doubtful_messages_and_is_checked():
    import json
    from src.agents.chat_signals import chat_signals_refined
    llm = _FakeLLM(json.dumps({"labels": [
        {"id": "chat_log[1]", "tone": "angry", "events": [], "why": "sarcasm"},
        {"id": "chat_log[2]", "tone": "frustrated", "events": ["bogus"]},
        {"id": "chat_log[0]", "tone": "calm"},            # not asked: ignored
        {"id": "chat_log[9]", "tone": "angry"},           # unknown id: ignored
    ]}))
    sig = await chat_signals_refined(CHAT, llm=llm)
    by = {m["source"]: m for m in sig["messages"]}
    assert "chat_log[0]" not in llm.calls[0][1]["content"].split("Label only these messages:")[1]
    assert by["chat_log[0]"]["tone"] == "frustrated" and by["chat_log[0]"]["decided_by"] == "code"
    assert by["chat_log[1]"]["tone"] == "angry" and by["chat_log[1]"]["decided_by"] == "llm"
    assert by["chat_log[2]"]["events"] == [] and sig["llm_checked"] == 2
    assert sig["overall"] == {"rider": "angry", "driver": "frustrated"}


@pytest.mark.asyncio
async def test_model_failure_or_nothing_doubtful_keeps_the_code_labels():
    from src.agents.chat_signals import chat_signals, chat_signals_refined
    sig = await chat_signals_refined(CHAT, llm=_FakeLLM(RuntimeError("quota")))
    assert sig["llm_checked"] == 0 and "quota" in sig["llm_error"]
    assert sig["messages"] == chat_signals(CHAT)["messages"]
    calm = _FakeLLM("{}")
    await chat_signals_refined([{"sender": "rider", "content": "I'm at the lobby"}], llm=calm)
    assert calm.calls == []                               # no doubtful message: no model call
