"""
Unified LLM Client
Uses Google Gemini API for chat completions.
"""
import google.generativeai as genai
from src.config import (
    LLM_API_KEY,
    LLM_MODEL,
    LLM_TEMPERATURE,
    LLM_MAX_TOKENS,
)


class LLMClient:
    """
    Unified LLM client wrapping Google Gemini API.
    """

    def __init__(self):
        self.api_key = LLM_API_KEY
        self.model = LLM_MODEL
        self.temperature = LLM_TEMPERATURE
        self.max_tokens = LLM_MAX_TOKENS
        self._configured = False
        self._client = None

    def _ensure_configured(self):
        if not self._configured:
            genai.configure(api_key=self.api_key)
            self._configured = True

    def _get_model(self):
        self._ensure_configured()
        if self._client is None:
            self._client = genai.GenerativeModel(f"models/{self.model}")
        return self._client

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

        response = chat.send_message(
            prompt,
            generation_config=generation_config,
        )

        text = response.text

        # Handle JSON response format request
        if response_format and response_format.get("type") == "json_object":
            # Gemini doesn't natively support JSON mode, so we wrap in instruction
            pass

        return text

    async def chat_json(
        self,
        messages: list[dict],
        temperature: float | None = None,
    ) -> str:
        """
        Send a chat request expecting JSON output.
        Returns the raw JSON string (caller should parse).
        """
        # Append JSON instruction to system message
        json_messages = list(messages)
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
        return await self.chat(
            messages=json_messages,
            temperature=temperature,
        )


# Singleton instance
llm_client = LLMClient()
