"""
Tests for LLMClient provider switching (Gemini default, Groq via OpenAI-compatible API).
No network: the Groq client is replaced with a fake.
"""
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from src.core import llm_client as llm_module
from src.core.llm_client import LLMClient
from src.core.trace import Tracer, set_tracer, step


class _FakeCompletions:
    def __init__(self, reply=None, error=None):
        self.calls, self.reply, self.error = [], reply, error

    async def create(self, **kwargs):
        self.calls.append(kwargs)
        if self.error:
            raise self.error
        msg = type("M", (), {"content": self.reply})()
        return type("R", (), {"choices": [type("C", (), {"message": msg})()]})()


def _groq_client(monkeypatch, reply='{"ok": true}', error=None) -> tuple[LLMClient, _FakeCompletions]:
    monkeypatch.setattr(llm_module, "LLM_PROVIDER", "groq")
    monkeypatch.setattr(llm_module, "GROQ_API_KEY", "test-key")
    monkeypatch.setattr(llm_module, "GROQ_MODEL", "test-model")
    client = LLMClient()
    completions = _FakeCompletions(reply, error)
    client._groq = type("G", (), {"chat": type("Ch", (), {"completions": completions})()})()
    return client, completions


def test_tests_run_on_gemini_path():
    # conftest pins the provider so fakes work and no test spends Groq quota
    assert LLMClient().provider == "gemini"


@pytest.mark.asyncio
async def test_groq_chat_sends_openai_messages(monkeypatch):
    client, fake = _groq_client(monkeypatch, reply="hello")
    out = await client.chat([{"role": "system", "content": "be brief"}, {"role": "user", "content": "hi"}])
    assert out == "hello"
    call = fake.calls[0]
    assert call["model"] == "test-model"
    assert call["messages"] == [{"role": "system", "content": "be brief"}, {"role": "user", "content": "hi"}]
    assert "response_format" not in call


@pytest.mark.asyncio
async def test_groq_chat_json_uses_json_mode(monkeypatch):
    client, fake = _groq_client(monkeypatch)
    out = await client.chat_json([{"role": "user", "content": "give json"}])
    assert out == '{"ok": true}'
    assert fake.calls[0]["response_format"] == {"type": "json_object"}
    assert "JSON" in fake.calls[0]["messages"][0]["content"]  # Groq JSON mode needs the word in the prompt


@pytest.mark.asyncio
async def test_groq_calls_are_traced_and_errors_raise(monkeypatch):
    client, _ = _groq_client(monkeypatch, reply="traced")
    tracer = Tracer()
    set_tracer(tracer)
    try:
        async with step("Agent", "t"):
            await client.chat([{"role": "user", "content": "q"}])
        bad, _ = _groq_client(monkeypatch, error=RuntimeError("429 rate limit"))
        with pytest.raises(RuntimeError):
            async with step("Agent", "t2"):
                await bad.chat([{"role": "user", "content": "q"}])
    finally:
        set_tracer(None)
    calls = [e for e in tracer.events if e["type"] == "llm_call"]
    assert calls[0]["response"] == "traced" and "[user]\nq" in calls[0]["prompt"]
    assert calls[1]["error"] and "429" in calls[1]["error"]


def test_groq_without_key_fails_clearly(monkeypatch):
    monkeypatch.setattr(llm_module, "LLM_PROVIDER", "groq")
    monkeypatch.setattr(llm_module, "GROQ_API_KEY", "")
    with pytest.raises(RuntimeError, match="GROQ_API_KEY"):
        LLMClient()._get_groq()


class _FakeAPIError(Exception):
    def __init__(self, status_code, code):
        super().__init__(f"Error code: {status_code}, code: {code}")
        self.status_code = status_code
        self.body = {"error": {"code": code}}


@pytest.mark.asyncio
async def test_groq_json_validation_error_retries_once(monkeypatch):
    client, fake = _groq_client(monkeypatch)
    first_call = fake.create

    async def fail_once(**kwargs):
        if not fake.calls:
            fake.calls.append(kwargs)
            raise _FakeAPIError(400, "json_validate_failed")
        return await first_call(**kwargs)

    fake.create = fail_once
    messages = [{"role": "system", "content": "Return the result."}]
    assert await client.chat_json(messages) == '{"ok": true}'
    assert len(fake.calls) == 2
    assert all(c["response_format"] == {"type": "json_object"} for c in fake.calls)
    assert all(c["messages"][0]["content"].count("Respond ONLY with valid JSON") == 1 for c in fake.calls)
    assert messages[0]["content"] == "Return the result."


@pytest.mark.asyncio
async def test_groq_json_validation_error_stops_after_second_failure(monkeypatch):
    client, fake = _groq_client(monkeypatch, error=_FakeAPIError(400, "json_validate_failed"))
    with pytest.raises(_FakeAPIError):
        await client.chat_json([{"role": "user", "content": "Return JSON"}])
    assert len(fake.calls) == 2


@pytest.mark.asyncio
@pytest.mark.parametrize("status_code,code", [
    (429, "rate_limit_exceeded"),
    (401, "invalid_api_key"),
    (400, "invalid_request"),
])
async def test_groq_json_retry_does_not_hide_other_errors(monkeypatch, status_code, code):
    client, fake = _groq_client(monkeypatch, error=_FakeAPIError(status_code, code))
    with pytest.raises(_FakeAPIError):
        await client.chat_json([{"role": "user", "content": "Return JSON"}])
    assert len(fake.calls) == 1
