"""
Shared test setup.

Tests always run against the Gemini code path, whatever LLM_PROVIDER says in a
developer's .env, so fakes that patch the Gemini model keep working and no test
spends Groq quota. Tests for the Groq path set the provider themselves.
"""
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from src.core import llm_client as llm_module


@pytest.fixture(autouse=True)
def _force_gemini_provider(monkeypatch):
    monkeypatch.setattr(llm_module, "LLM_PROVIDER", "gemini")
