"""
LLM Fallback Analyzer: when deterministic regex/AST analysis fails to locate
payment logic (e.g. in novel or heavily obfuscated architectures), optionally
queries the configured AI model to locate payment-related files.
"""

import json
import os
from pathlib import Path
from typing import Optional

import requests
from dotenv import load_dotenv

load_dotenv()


def call_llm_text(system_prompt: str, user_prompt: str) -> Optional[str]:
    """Call the configured AI provider using plain HTTP, matching ai_engine's provider setup."""
    provider = os.getenv("AI_PROVIDER", "gemini").strip().lower()
    api_key = ""

    if provider == "gemini":
        api_key = os.getenv("GOOGLE_API_KEY", "").strip()
        if not api_key:
            return None
        model = os.getenv("AI_MODEL", "gemini-1.5-flash")
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={api_key}"
        payload = {
            "contents": [
                {"role": "user", "parts": [{"text": f"{system_prompt}\n\n{user_prompt}"}]}
            ],
            "generationConfig": {"temperature": 0.0},
        }
        try:
            resp = requests.post(url, json=payload, timeout=30)
            if resp.ok:
                data = resp.json()
                return data["candidates"][0]["content"]["parts"][0]["text"]
        except Exception:
            return None

    elif provider == "openai":
        api_key = os.getenv("OPENAI_API_KEY", "").strip()
        if not api_key:
            return None
        model = os.getenv("AI_MODEL", "gpt-4o-mini")
        url = "https://api.openai.com/v1/chat/completions"
        headers = {"Authorization": f"Bearer {api_key}"}
        payload = {
            "model": model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "temperature": 0.0,
        }
        try:
            resp = requests.post(url, headers=headers, json=payload, timeout=30)
            if resp.ok:
                return resp.json()["choices"][0]["message"]["content"]
        except Exception:
            return None

    elif provider == "anthropic":
        api_key = os.getenv("ANTHROPIC_API_KEY", "").strip()
        if not api_key:
            return None
        model = os.getenv("AI_MODEL", "claude-3-5-sonnet-20241022")
        url = "https://api.anthropic.com/v1/messages"
        headers = {
            "x-api-key": api_key,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
        }
        payload = {
            "model": model,
            "max_tokens": 1000,
            "system": system_prompt,
            "messages": [{"role": "user", "content": user_prompt}],
            "temperature": 0.0,
        }
        try:
            resp = requests.post(url, headers=headers, json=payload, timeout=30)
            if resp.ok:
                return resp.json()["content"][0]["text"]
        except Exception:
            return None

    return None


def resolve_unidentified_payment_files(repo_root: Path, file_list: list[str]) -> list[str]:
    """Ask LLM to identify which files in a repository likely contain payment handling."""
    system_prompt = (
        "You are an expert code analyst. Given a list of repository file paths, identify which "
        "files contain checkout forms, payment processing, or PayPal integrations. "
        "Return a valid JSON array of string file paths, nothing else."
    )
    user_prompt = f"Repository files:\n{json.dumps(file_list, indent=2)}\n\nIdentify payment files:"

    text = call_llm_text(system_prompt, user_prompt)
    if not text:
        return []

    try:
        cleaned = text.strip()
        if cleaned.startswith("```"):
            cleaned = cleaned.split("```")[1]
            if cleaned.startswith("json"):
                cleaned = cleaned[4:]
        data = json.loads(cleaned.strip())
        if isinstance(data, list):
            return [str(item) for item in data if isinstance(item, str)]
    except Exception:
        pass

    return []
