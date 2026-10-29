"""D66: harassment told in plain words, or done in the chat, reaches a person (LX-15)."""
import pytest

from src.agents.classifier import ClassifierAgent, UrgencyLevel
from src.agents.collector import DisputeContext, DisputeType
from src.agents.fraud import chat_label_signals, keyword_chat_labels
from src.agents.policy_gates import safety_indicators
from src.agents.safety import harassment_in_claim, harassment_in_message

LX15_CLAIM = ("The driver ended the trip a bit short of the entrance, but the real problem is that he kept "
              "asking personal questions about my boyfriend, told me to sit in the front seat, made comments "
              "about how I look, and then messaged me after the trip asking for my number. I felt "
              "uncomfortable the whole ride. I want a credit and I want this reported.")
LX15_CHAT = [
    {"sender": "driver", "message": "Hi, I am at the front of the Bugis+ entrance, black Wish."},
    {"sender": "driver", "message": "you look really nice tonight. can I have your number? maybe dinner "
                                    "this weekend, I will drive you for free"},
    {"sender": "rider", "message": "Please stop messaging me. You kept asking about my boyfriend in the car "
                                   "and told me to sit in front."},
]


@pytest.mark.asyncio
async def test_lx15_complaint_is_p0():
    ctx = DisputeContext(dispute_id="LX-15", reporter="rider", order_id="R", description=LX15_CLAIM,
                         type=DisputeType.SERVICE_QUALITY)
    result = await ClassifierAgent().classify(ctx)
    assert result.urgency == UrgencyLevel.P0 and result.requires_human


def test_advance_from_the_other_party_is_a_safety_alert():
    found = keyword_chat_labels(LX15_CHAT, "rider")
    signals, safety = chat_label_signals(found, "R-1")
    assert [f["label"] for f in found] == ["harassment"]
    assert len(safety) == 1 and "can I have your number" in safety[0]
    assert signals == []            # kept out of the fraud score


def test_the_filer_quoting_an_advance_is_not_one():
    chat = [{"sender": "rider", "message": "He said you look really nice and can I have your number"}]
    assert keyword_chat_labels(chat, "rider") == []


def test_policy_gate_sees_plain_word_harassment():
    assert "asking for my number" in safety_indicators({"description": LX15_CLAIM})


@pytest.mark.parametrize("text", [
    "I had no food or drink with me. Please check the photos.",          # LX-14
    "I had no drink with me. The seat was spotless when I got out.",     # OF-30
    "Can I have your number for the lost item report?",
    "The driver asked if he could drop me at the front gate.",
])
def test_ordinary_words_are_not_advances(text):
    assert harassment_in_message(text) == [] and harassment_in_claim(text) == []
