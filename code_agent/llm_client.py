"""
LLM Client Configurator for CheckoutPilot Code Agent.

Supports free & open models:
- Google Gemini (gemini-1.5-flash via Google AI Studio free tier)
- NVIDIA NIM / NeMo (integrate.api.nvidia.com)
- Local Ollama (http://localhost:11434/v1)
- Deterministic Offline Fallback (zero API calls, 100% reliable)
"""

import json
import os
from abc import ABC, abstractmethod
from typing import Any, Optional

import requests
from dotenv import load_dotenv

load_dotenv()


class BaseLLMAdapter(ABC):
    """Abstract interface for LLM providers."""

    @abstractmethod
    def generate_text(self, prompt: str, system_prompt: Optional[str] = None) -> Optional[str]:
        """Generate text from the model."""
        pass

    def generate_json(self, prompt: str, system_prompt: Optional[str] = None) -> Optional[Any]:
        """Generate parsed JSON from the model."""
        text = self.generate_text(prompt, system_prompt)
        if not text:
            return None
        cleaned = text.strip()
        if cleaned.startswith("```"):
            parts = cleaned.split("```")
            if len(parts) >= 2:
                cleaned = parts[1]
                if cleaned.startswith("json"):
                    cleaned = cleaned[4:]
        try:
            return json.loads(cleaned.strip())
        except Exception:
            return None

    @abstractmethod
    def is_available(self) -> bool:
        """Check if provider credentials/endpoints are configured."""
        pass


class GeminiAdapter(BaseLLMAdapter):
    """Google Gemini adapter (uses free tier on Google AI Studio)."""

    def __init__(self, api_key: Optional[str] = None, model: Optional[str] = None):
        self.api_key = (api_key or os.getenv("GOOGLE_API_KEY", "")).strip()
        self.model = model or os.getenv("AI_MODEL", "gemini-1.5-flash")

    def is_available(self) -> bool:
        return bool(self.api_key)

    def generate_text(self, prompt: str, system_prompt: Optional[str] = None) -> Optional[str]:
        if not self.is_available():
            return None
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{self.model}:generateContent?key={self.api_key}"
        full_text = f"{system_prompt}\n\n{prompt}" if system_prompt else prompt
        payload = {
            "contents": [{"role": "user", "parts": [{"text": full_text}]}],
            "generationConfig": {"temperature": 0.0},
        }
        try:
            resp = requests.post(url, json=payload, timeout=30)
            if resp.ok:
                data = resp.json()
                return data["candidates"][0]["content"]["parts"][0]["text"]
        except Exception:
            pass
        return None


class NvidiaAdapter(BaseLLMAdapter):
    """NVIDIA NIM / NeMo adapter (OpenAI-compatible endpoints on integrate.api.nvidia.com)."""

    def __init__(self, api_key: Optional[str] = None, model: Optional[str] = None, base_url: Optional[str] = None):
        self.api_key = (api_key or os.getenv("NVIDIA_API_KEY", "")).strip()
        self.model = model or os.getenv("AI_MODEL", "mistralai/codestral-22b")
        self.base_url = (base_url or os.getenv("AI_BASE_URL", "https://integrate.api.nvidia.com/v1")).rstrip("/")

    def is_available(self) -> bool:
        return bool(self.api_key)

    def generate_text(self, prompt: str, system_prompt: Optional[str] = None) -> Optional[str]:
        if not self.is_available():
            return None
        url = f"{self.base_url}/chat/completions"
        headers = {"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"}
        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})

        payload = {"model": self.model, "messages": messages, "temperature": 0.0}
        try:
            resp = requests.post(url, headers=headers, json=payload, timeout=30)
            if resp.ok:
                return resp.json()["choices"][0]["message"]["content"]
        except Exception:
            pass
        return None


class OllamaAdapter(BaseLLMAdapter):
    """Local Ollama adapter (100% free, runs offline on localhost)."""

    def __init__(self, model: Optional[str] = None, base_url: Optional[str] = None):
        self.model = model or os.getenv("AI_MODEL", "qwen2.5-coder")
        self.base_url = (base_url or os.getenv("AI_BASE_URL", "http://localhost:11434/v1")).rstrip("/")

    def is_available(self) -> bool:
        try:
            resp = requests.get(f"{self.base_url}/models", timeout=2)
            return resp.ok
        except Exception:
            return False

    def generate_text(self, prompt: str, system_prompt: Optional[str] = None) -> Optional[str]:
        url = f"{self.base_url}/chat/completions"
        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})
        payload = {"model": self.model, "messages": messages, "temperature": 0.0}
        try:
            resp = requests.post(url, json=payload, timeout=30)
            if resp.ok:
                return resp.json()["choices"][0]["message"]["content"]
        except Exception:
            pass
        return None


class DeterministicFallbackAdapter(BaseLLMAdapter):
    """Zero-cost offline fallback that provides deterministic responses without API calls."""

    def is_available(self) -> bool:
        return True

    def generate_text(self, prompt: str, system_prompt: Optional[str] = None) -> Optional[str]:
        return "Deterministic offline analysis: rule-based fallback active."


def get_llm_client() -> BaseLLMAdapter:
    """Factory function returning the configured LLM adapter based on .env settings."""
    provider = os.getenv("AI_PROVIDER", "deterministic").strip().lower()

    if provider in ("gemini", "google"):
        adapter = GeminiAdapter()
        if adapter.is_available():
            return adapter

    if provider in ("nvidia", "nemo"):
        adapter = NvidiaAdapter()
        if adapter.is_available():
            return adapter

    if provider == "ollama":
        adapter = OllamaAdapter()
        if adapter.is_available():
            return adapter

    # Default fallback
    return DeterministicFallbackAdapter()

