"""
Unified LLM Client
Chat completions through Google Gemini (default), Groq, Cerebras or Tencent Hunyuan,
picked by LLM_PROVIDER in .env. The last three use the OpenAI-compatible API, so agents
keep the same chat() / chat_json() calls whichever provider is active. When a call fails,
the providers in LLM_FALLBACK_PROVIDERS are tried in order.
"""
import asyncio
import contextvars
import logging
import os
import re
import time

import google.generativeai as genai
from src.core.trace import record_llm_call
from src.config import (
    CEREBRAS_API_KEY,
    CEREBRAS_BASE_URL,
    CEREBRAS_MODEL,
    LLM_PRICE_IN_PER_M,
    LLM_PRICE_OUT_PER_M,
    LLM_SPEND_CAP_USD,
    GROQ_API_KEY,
    GROQ_BASE_URL,
    GROQ_MODEL,
    HUNYUAN_API_KEY,
    HUNYUAN_BASE_URL,
    HUNYUAN_MODEL,
    LLM_FALLBACK_PROVIDERS,
    LLM_API_KEY,
    LLM_MODEL,
    LLM_PROVIDER,
    LLM_TEMPERATURE,
    LLM_MAX_TOKENS,
)

logger = logging.getLogger(__name__)


# Free-tier default: 5 generate-content requests per minute, per project/model.
# Space calls across all agent instances in this server process. Paid projects
# can lower the interval via LLM_MIN_REQUEST_INTERVAL_SECONDS.
_MIN_INTERVAL_SECONDS = max(0.0, float(os.getenv("LLM_MIN_REQUEST_INTERVAL_SECONDS", "13")))
_rate_lock = asyncio.Lock()
_next_request_at = 0.0


async def _wait_for_request_slot() -> float:
    """Wait for the next free request slot; returns the seconds spent waiting."""
    global _next_request_at
    t0 = time.monotonic()
    async with _rate_lock:
        delay = max(0.0, _next_request_at - time.monotonic())
        if delay:
            await asyncio.sleep(delay)
        _next_request_at = time.monotonic() + _MIN_INTERVAL_SECONDS
    return time.monotonic() - t0


# Seconds the OpenAI SDK is told to wait on each 429 during the current Groq call
# (read from the retry-after headers), so traces can report rate-limit waiting
# separately from model time.
_groq_rate_waits: contextvars.ContextVar[list | None] = contextvars.ContextVar("groq_rate_waits", default=None)


async def _on_groq_response(response) -> None:
    waits = _groq_rate_waits.get()
    if waits is None or response.status_code != 429:
        return
    try:
        ms = response.headers.get("retry-after-ms")
        seconds = float(ms) / 1000 if ms else float(response.headers.get("retry-after", "1"))
    except ValueError:
        seconds = 1.0
    waits.append(min(seconds, 60.0))

# Estimated USD spent by this process on the paid Cerebras credit.
_spent_usd = 0.0


class SpendCapReached(RuntimeError):
    pass


def _groq_json_validation_failed(exc: Exception) -> bool:
    """Only Groq's malformed JSON response is safe to retry as a new request."""
    if getattr(exc, "status_code", None) != 400:
        return False
    body = getattr(exc, "body", None)
    if isinstance(body, dict):
        error = body.get("error", body)
        if isinstance(error, dict) and error.get("code") == "json_validate_failed":
            return True
    return "json_validate_failed" in str(exc).lower()


class LLMClient:
    """
    Unified LLM client: one primary provider plus optional fallback providers.
    """

    def __init__(self, provider: str | None = None, fallbacks: list[str] | None = None):
        self.provider = provider or LLM_PROVIDER
        if self.provider == "cerebras":
            self.api_key, self.model, self.base_url = CEREBRAS_API_KEY, CEREBRAS_MODEL, CEREBRAS_BASE_URL
        elif self.provider == "groq":
            self.api_key, self.model, self.base_url = GROQ_API_KEY, GROQ_MODEL, GROQ_BASE_URL
        elif self.provider == "hunyuan":
            self.api_key, self.model, self.base_url = HUNYUAN_API_KEY, HUNYUAN_MODEL, HUNYUAN_BASE_URL
        else:
            self.api_key, self.model, self.base_url = LLM_API_KEY, LLM_MODEL, None
        # Cerebras and Hunyuan are OpenAI-compatible, so they share the Groq code path
        self.openai_compatible = self.provider in ("groq", "cerebras", "hunyuan")
        # Backup providers (built on first use), never including the primary itself
        names = LLM_FALLBACK_PROVIDERS if fallbacks is None else fallbacks
        self._fallback_names = [n for n in dict.fromkeys(names) if n != self.provider]
        self._fallback_clients: dict[str, "LLMClient"] = {}
        self.temperature = LLM_TEMPERATURE
        self.max_tokens = LLM_MAX_TOKENS
        self._configured = False
        self._client = None
        self._groq = None

    def _get_groq(self):
        if self._groq is None:
            from openai import AsyncOpenAI
            if not self.api_key:
                raise RuntimeError(f"LLM_PROVIDER={self.provider} but {self.provider.upper()}_API_KEY is not set in .env")
            import httpx
            # max_retries: the SDK waits out 429s (honouring retry-after) before giving up
            self._groq = AsyncOpenAI(
                api_key=self.api_key, base_url=self.base_url, max_retries=4,
                http_client=httpx.AsyncClient(timeout=120, event_hooks={"response": [_on_groq_response]}),
            )
        return self._groq

    async def _chat_groq(self, messages, temperature, max_tokens, response_format,
                         reasoning_effort: str | None = None) -> str:
        """One chat completion on Groq, recorded in the trace like the Gemini path."""
        global _spent_usd
        if self.provider == "cerebras" and _spent_usd >= LLM_SPEND_CAP_USD:
            raise SpendCapReached(f"Spend cap reached: ~${_spent_usd:.4f} of ${LLM_SPEND_CAP_USD:.2f}")
        prompt = "\n\n".join(f"[{m.get('role', 'user')}]\n{m.get('content', '')}" for m in messages)
        kwargs = {
            "model": self.model,
            "messages": [{"role": m.get("role", "user"), "content": m.get("content", "")} for m in messages],
            "temperature": temperature if temperature is not None else self.temperature,
            "max_tokens": max_tokens if max_tokens is not None else self.max_tokens,
        }
        if response_format:
            kwargs["response_format"] = response_format
        if reasoning_effort:
            kwargs["reasoning_effort"] = reasoning_effort
        waits: list[float] = []
        # Cerebras free tier allows 5 requests/min and 150/hour: space calls out
        if self.provider == "cerebras":
            waits.append(await _wait_for_request_slot())
        token = _groq_rate_waits.set(waits)
        t0 = time.perf_counter()
        try:
            response = await self._get_groq().chat.completions.create(**kwargs)
            text = response.choices[0].message.content or ""
            if not text.strip() and response.choices[0].finish_reason == "length":
                # A reasoning model can spend the whole budget thinking and return no answer
                logger.warning("Empty answer: max_tokens=%s used up (reasoning model); raise it",
                               kwargs["max_tokens"])
        except Exception as exc:
            record_llm_call(prompt, None, int((time.perf_counter() - t0) * 1000), error=str(exc),
                            wait_ms=int(sum(waits) * 1000))
            raise
        finally:
            _groq_rate_waits.reset(token)
        usage = None
        if getattr(response, "usage", None):
            usage = {"prompt_tokens": response.usage.prompt_tokens,
                     "completion_tokens": response.usage.completion_tokens}
            if self.provider == "cerebras":
                _spent_usd += (response.usage.prompt_tokens * LLM_PRICE_IN_PER_M
                               + response.usage.completion_tokens * LLM_PRICE_OUT_PER_M) / 1_000_000
        record_llm_call(prompt, text, int((time.perf_counter() - t0) * 1000),
                        usage=usage, wait_ms=int(sum(waits) * 1000))
        return text

    def _ensure_configured(self):
        if not self._configured:
            genai.configure(api_key=self.api_key)
            self._configured = True

    def _get_model(self):
        self._ensure_configured()
        if self._client is None:
            self._client = genai.GenerativeModel(f"models/{self.model}")
        return self._client

    async def _chat_primary(
        self,
        messages: list[dict],
        temperature: float | None = None,
        max_tokens: int | None = None,
        response_format: dict | None = None,
        reasoning_effort: str | None = None,
    ) -> str:
        """
        Send a chat completion request and return the response text.
        reasoning_effort only applies to OpenAI-compatible providers (gpt-oss).

        Args:
            messages: List of {role, content} dicts
            temperature: Override default temperature if needed
            max_tokens: Override default max_tokens if needed
            response_format: Optional dict like {"type": "json_object"}

        Returns:
            The assistant's response text
        """
        if self.openai_compatible:
            return await self._chat_groq(messages, temperature, max_tokens, response_format, reasoning_effort)

        model = self._get_model()

        # Convert OpenAI-style messages to Gemini format
        gemini_messages = []
        system_parts = []
        for msg in messages:
            role = msg.get("role", "user")
            content = msg.get("content", "")
            if role == "system":
                system_parts.append(content)
            elif role == "user":
                gemini_messages.append({"role": "user", "parts": [content]})
            elif role == "assistant":
                gemini_messages.append({"role": "model", "parts": [content]})

        # Build generation config
        generation_config = {
            "temperature": temperature if temperature is not None else self.temperature,
            "max_output_tokens": max_tokens if max_tokens is not None else self.max_tokens,
        }

        # Start chat with history
        chat = model.start_chat(history=gemini_messages[:-1] if len(gemini_messages) > 1 else [])

        # Send the last user message
        last_msg = gemini_messages[-1] if gemini_messages else {"parts": [""]}
        prompt = "\n".join(system_parts) + "\n" + last_msg["parts"][0] if system_parts else last_msg["parts"][0]

        # send_message is blocking: run it in a thread so the event loop (and the
        # live trace stream) keeps running during the call
        t0 = time.perf_counter()
        waited = 0.0
        try:
            for attempt in range(2):
                waited += await _wait_for_request_slot()
                try:
                    response = await asyncio.to_thread(
                        chat.send_message,
                        prompt,
                        generation_config=generation_config,
                    )
                    break
                except Exception as exc:
                    message = str(exc)
                    if attempt == 0 and "GenerateRequestsPerMinute" in message:
                        match = re.search(r"Please retry in ([0-9.]+)s", message)
                        delay = float(match.group(1)) if match else 60.0
                        delay = min(120.0, max(1.0, delay + 1.0))
                        waited += delay
                        await asyncio.sleep(delay)
                        continue
                    raise
            text = response.text
        except Exception as exc:
            record_llm_call(prompt, None, int((time.perf_counter() - t0) * 1000), error=str(exc),
                            wait_ms=int(waited * 1000))
            raise
        meta = getattr(response, "usage_metadata", None)
        usage = None
        if meta is not None:
            usage = {"prompt_tokens": getattr(meta, "prompt_token_count", None),
                     "completion_tokens": getattr(meta, "candidates_token_count", None)}
        record_llm_call(prompt, text, int((time.perf_counter() - t0) * 1000),
                        usage=usage, wait_ms=int(waited * 1000))

        # Handle JSON response format request
        if response_format and response_format.get("type") == "json_object":
            # Gemini doesn't natively support JSON mode, so we wrap in instruction
            pass

        return text

    async def _chat_json_primary(
        self,
        messages: list[dict],
        temperature: float | None = None,
        reasoning_effort: str | None = None,
    ) -> str:
        """
        Send a chat request expecting JSON output on this client's provider only.
        Returns the raw JSON string (caller should parse).
        """
        # Append JSON instruction to system message
        json_messages = [dict(m) for m in messages]
        has_system = any(m.get("role") == "system" for m in json_messages)
        if has_system:
            for m in json_messages:
                if m.get("role") == "system":
                    m["content"] += "\nRespond ONLY with valid JSON. No markdown, no explanations."
                    break
        else:
            json_messages.insert(0, {
                "role": "system",
                "content": "Respond ONLY with valid JSON. No markdown, no explanations."
            })
        response_format = {"type": "json_object"} if self.openai_compatible else None
        try:
            return await self._chat_primary(
                messages=json_messages,
                temperature=temperature,
                response_format=response_format,
                reasoning_effort=reasoning_effort,
            )
        except Exception as exc:
            if not self.openai_compatible or not _groq_json_validation_failed(exc):
                raise
            # One fresh attempt for transient JSON-mode validation errors.
            # The first failed call is traced by _chat_groq for accurate usage.
            return await self._chat_primary(
                messages=json_messages,
                temperature=temperature,
                response_format=response_format,
                reasoning_effort=reasoning_effort,
            )


    def _chain(self) -> list["LLMClient"]:
        """This client, then each fallback provider in order."""
        for name in self._fallback_names:
            if name not in self._fallback_clients:
                self._fallback_clients[name] = LLMClient(provider=name, fallbacks=[])
        return [self] + [self._fallback_clients[n] for n in self._fallback_names]

    async def _with_fallback(self, method: str, **kwargs) -> str:
        chain = self._chain()
        for i, client in enumerate(chain):
            try:
                return await getattr(client, method)(**kwargs)
            except Exception as exc:
                if i == len(chain) - 1:
                    raise
                # The failed call is already in the trace; say which provider takes over
                logger.warning("LLM provider %s failed (%s); falling back to %s",
                               client.provider, str(exc)[:200], chain[i + 1].provider)

    async def chat(
        self,
        messages: list[dict],
        temperature: float | None = None,
        max_tokens: int | None = None,
        response_format: dict | None = None,
        reasoning_effort: str | None = None,
    ) -> str:
        """Chat completion on the primary provider, then on each fallback if it fails."""
        return await self._with_fallback(
            "_chat_primary", messages=messages, temperature=temperature, max_tokens=max_tokens,
            response_format=response_format, reasoning_effort=reasoning_effort)

    async def chat_json(
        self,
        messages: list[dict],
        temperature: float | None = None,
        reasoning_effort: str | None = None,
    ) -> str:
        """JSON chat on the primary provider, then on each fallback if it fails.
        Returns the raw JSON string (caller should parse)."""
        return await self._with_fallback(
            "_chat_json_primary", messages=messages, temperature=temperature,
            reasoning_effort=reasoning_effort)


# Singleton instance
llm_client = LLMClient()
