"""
Unified LLM Client
Uses OpenAI-compatible API format to support Tencent Hunyuan and other providers.
"""
from openai import AsyncOpenAI
from src.config import (
    LLM_API_KEY,
    LLM_BASE_URL,
    LLM_MODEL,
    LLM_TEMPERATURE,
    LLM_MAX_TOKENS,
)


class LLMClient:
    """
    Unified LLM client wrapping OpenAI-compatible API.
    Works with Tencent Hunyuan, OpenAI, Deepseek, etc.
    """

    def __init__(self):
        self.api_key = LLM_API_KEY
        self.client = AsyncOpenAI(api_key=LLM_API_KEY or "placeholder", base_url=LLM_BASE_URL)
        self.model = LLM_MODEL
        self.temperature = LLM_TEMPERATURE
        self.max_tokens = LLM_MAX_TOKENS

    async def chat(
        self,
        messages: list[dict],
        temperature: float | None = None,
        max_tokens: int | None = None,
        response_format: dict | None = None,
    ) -> str:
        """
        Send a chat completion request and return the response text.

        Args:
            messages: List of {role, content} dicts
            temperature: Override default temperature if needed
            max_tokens: Override default max_tokens if needed
            response_format: Optional dict like {"type": "json_object"}

        Returns:
            The assistant's response text
        """
        kwargs = {
            "model": self.model,
            "messages": messages,
            "temperature": temperature if temperature is not None else self.temperature,
            "max_tokens": max_tokens if max_tokens is not None else self.max_tokens,
        }
        if response_format:
            kwargs["response_format"] = response_format

        response = await self.client.chat.completions.create(**kwargs)
        return response.choices[0].message.content

    async def chat_json(
        self,
        messages: list[dict],
        temperature: float | None = None,
    ) -> str:
        """
        Send a chat request expecting JSON output.
        Returns the raw JSON string (caller should parse).
        """
        return await self.chat(
            messages=messages,
            temperature=temperature,
            response_format={"type": "json_object"},
        )


# Singleton instance
llm_client = LLMClient()
