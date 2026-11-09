"""
Tests for the multi-provider LLM configurator.
"""

import os
from code_agent.llm_client import (
    DeterministicFallbackAdapter,
    GeminiAdapter,
    NvidiaAdapter,
    OllamaAdapter,
    get_llm_client,
)


def test_deterministic_fallback():
    """Verify offline fallback produces deterministic output without API keys."""
    client = DeterministicFallbackAdapter()
    assert client.is_available() is True
    text = client.generate_text("test prompt")
    assert text is not None
    assert "Deterministic" in text


def test_gemini_adapter_availability():
    """Verify Gemini adapter reports availability based on GOOGLE_API_KEY."""
    adapter_no_key = GeminiAdapter(api_key="")
    assert adapter_no_key.is_available() is False

    adapter_with_key = GeminiAdapter(api_key="AIzaSyDummyKey")
    assert adapter_with_key.is_available() is True


def test_nvidia_adapter_availability():
    """Verify NVIDIA adapter reports availability based on NVIDIA_API_KEY."""
    adapter_no_key = NvidiaAdapter(api_key="")
    assert adapter_no_key.is_available() is False

    adapter_with_key = NvidiaAdapter(api_key="nvapi-dummy-key")
    assert adapter_with_key.is_available() is True
    assert adapter_with_key.base_url == "https://integrate.api.nvidia.com/v1"


def test_factory_returns_client():
    """Verify get_llm_client returns a working adapter."""
    client = get_llm_client()
    assert client.is_available() is True

