import asyncio
import time
from types import SimpleNamespace

import pytest

from src.core import llm_client


@pytest.mark.asyncio
async def test_gemini_calls_from_different_agents_share_one_rate_limit(monkeypatch):
    starts = []

    class FakeChat:
        def send_message(self, *_args, **_kwargs):
            starts.append(time.monotonic())
            return SimpleNamespace(text="ok")

    monkeypatch.setattr(
        llm_client.LLMClient, "_get_model",
        lambda self: SimpleNamespace(start_chat=lambda **kwargs: FakeChat()),
    )
    monkeypatch.setattr(llm_client, "_MIN_INTERVAL_SECONDS", 0.03)
    monkeypatch.setattr(llm_client, "_next_request_at", 0.0)

    calls = [
        llm_client.LLMClient().chat([{"role": "user", "content": "test"}])
        for _ in range(3)
    ]
    assert await asyncio.gather(*calls) == ["ok", "ok", "ok"]
    assert len(starts) == 3
    assert min(b - a for a, b in zip(starts, starts[1:])) >= 0.025


@pytest.mark.asyncio
async def test_per_minute_quota_error_retries_once(monkeypatch):
    attempts = []

    class FakeChat:
        def send_message(self, *_args, **_kwargs):
            attempts.append(1)
            if len(attempts) == 1:
                raise RuntimeError(
                    "429 GenerateRequestsPerMinutePerProjectPerModel-FreeTier "
                    "Please retry in 0.001s"
                )
            return SimpleNamespace(text="recovered")

    monkeypatch.setattr(
        llm_client.LLMClient, "_get_model",
        lambda self: SimpleNamespace(start_chat=lambda **kwargs: FakeChat()),
    )
    monkeypatch.setattr(llm_client, "_MIN_INTERVAL_SECONDS", 0.0)
    monkeypatch.setattr(llm_client, "_next_request_at", 0.0)

    result = await llm_client.LLMClient().chat(
        [{"role": "user", "content": "test"}]
    )
    assert result == "recovered"
    assert len(attempts) == 2


@pytest.mark.asyncio
async def test_queue_full_429_is_retried_but_daily_cap_is_not(monkeypatch):
    """D30: a Cerebras 'queue_exceeded' 429 failed a Judge call; it is now retried."""
    from types import SimpleNamespace
    import src.core.llm_client as lc
    sleeps = []

    async def no_sleep(s):
        sleeps.append(s)
    monkeypatch.setattr(lc.asyncio, "sleep", no_sleep)
    monkeypatch.setattr(lc, "_wait_for_request_slot", lambda: _zero())

    async def _zero():
        return 0.0

    def client_with(errors):
        calls = {"n": 0}

        async def create(**kwargs):
            calls["n"] += 1
            if errors:
                raise errors.pop(0)
            msg = SimpleNamespace(content="{}")
            return SimpleNamespace(choices=[SimpleNamespace(message=msg, finish_reason="stop")], usage=None)
        c = object.__new__(lc.LLMClient)
        c.provider, c.model, c.temperature, c.max_tokens = "groq", "m", 0.1, 100
        c._get_groq = lambda: SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create)))
        return c, calls

    c, calls = client_with([RuntimeError("429 queue_exceeded"), RuntimeError("429 queue_exceeded")])
    args = dict(messages=[{"role": "user", "content": "x"}], temperature=None, max_tokens=None, response_format=None)
    assert await c._chat_groq(**args) == "{}"
    assert calls["n"] == 3 and sleeps == [20, 40]
    c, calls = client_with([RuntimeError("429 token_quota_exceeded")])
    with pytest.raises(RuntimeError):
        await c._chat_groq(**args)
    assert calls["n"] == 1
