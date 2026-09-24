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
