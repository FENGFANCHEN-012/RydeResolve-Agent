"""Query rewrite guard: a rewrite that adds a number the complaint never stated is rejected."""
import pytest

from src.rag.guarded_rewrite import check_rewrite, rewrite_query

# Real outputs of the earlier prompt (data/eval/retrieval/rewrites.json)
Q04_QUESTION = "What are the conditions for charging a rider a no-show fee?"
Q04_REWRITE = "no-show fee, driver, when rider does not board within 5 minutes of driver arrival"  # invented 5
Q02_COMPLAINT = ("I cancelled about five minutes after the driver accepted and got charged $6.61. "
                 "That's ridiculous, the driver hadn't even arrived yet. I want my money back.")
Q02_REWRITE = "cancellation fee, rider, cancelled 5 min after acceptance, driver not arrived, $6.61 charge"


def test_invented_number_is_rejected():
    assert "5" in check_rewrite(Q04_QUESTION, Q04_REWRITE)


def test_number_written_as_a_word_is_not_invented():
    # "about five minutes" -> "5 min" restates the complaint; it must not be rejected
    assert check_rewrite(Q02_COMPLAINT, Q02_REWRITE) is None


def test_numbers_from_the_complaint_are_allowed():
    assert check_rewrite(Q02_COMPLAINT, "rider cancellation fee $6.61 driver not arrived refund request") is None


def test_same_amount_written_differently_is_not_a_new_number():
    assert check_rewrite("I was charged $8.00", "no-show fee $8 charged") is None


def test_empty_or_long_rewrite_is_rejected():
    assert check_rewrite("x", "  ") == "empty"
    assert "longer" in check_rewrite("x", " ".join(["word"] * 40))


class FakeLLM:
    def __init__(self, reply=None, fail=False):
        self.reply, self.fail = reply, fail

    async def chat(self, messages, **_):
        if self.fail:
            raise RuntimeError("quota")
        return self.reply


@pytest.mark.asyncio
async def test_rewrite_uses_last_line_and_passes_guard():
    q, note = await rewrite_query(Q02_COMPLAINT, FakeLLM("thinking...\ncancellation fee driver not arrived refund"))
    assert q == "cancellation fee driver not arrived refund" and note == "ok"


@pytest.mark.asyncio
async def test_rejected_or_failed_rewrite_returns_none():
    assert (await rewrite_query(Q04_QUESTION, FakeLLM(Q04_REWRITE)))[0] is None
    assert (await rewrite_query(Q02_COMPLAINT, FakeLLM(fail=True)))[0] is None
