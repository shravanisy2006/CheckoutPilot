"""
Vision-model checks on checkout screenshots.

Sends cart and checkout screenshots to a vision-capable AI model and turns its
JSON answer into CheckoutIssue dictionaries.

Provider is chosen with AI_PROVIDER in .env: "anthropic", "openai" or "gemini".
The model can be overridden with AI_MODEL, and AI_FALLBACK_MODEL sets a backup
model used when the main one is busy. Busy/rate-limited replies are retried
automatically. Calls use plain HTTP (requests), so no extra SDK is needed.
Temperature is always 0 so results are repeatable.

Failures raise ModuleError:
    AI_UNAVAILABLE  no API key, network error, or provider error
    AI_BAD_OUTPUT   model answered twice with invalid JSON / wrong shape
"""

import base64
import hashlib
import json
import os
import time
from pathlib import Path
from typing import Callable, Literal

import requests
from dotenv import load_dotenv
from pydantic import BaseModel, Field, ValidationError

from ai_engine.errors import AI_BAD_OUTPUT, AI_UNAVAILABLE, ModuleError
from ai_engine.prompts import (
    PROMPT_VERSION,
    RETRY_NOTE,
    SYSTEM_PROMPT,
    VISION_ISSUE_CATALOGUE,
    build_user_prompt,
)
from ai_engine.rules import get_pages, make_issue

load_dotenv()

# A model caller takes (system prompt, user prompt, list of PNG bytes) and returns raw text.
ModelCaller = Callable[[str, str, list[bytes]], str]

MAX_IMAGES = 4                     # keeps cost and latency low
MAX_IMAGE_BYTES = 4_500_000        # providers reject very large images
# Newer "thinking" models can be slow with images; change with AI_TIMEOUT_SECONDS in .env.
REQUEST_TIMEOUT_SECONDS = int(os.getenv("AI_TIMEOUT_SECONDS", "120") or 120)
RETRYABLE_STATUS = {429, 500, 502, 503, 504}   # busy / rate limited: usually temporary
RETRY_WAITS_SECONDS = (3, 8)                   # wait 3 s, then 8 s, before giving up

DEFAULT_MODELS = {
    "anthropic": "claude-sonnet-4-5",
    "openai": "gpt-4o-mini",
    "gemini": "gemini-3.8-flash",  # 2.5-flash is no longer offered to new users
}
API_KEY_VARS = {
    "anthropic": "ANTHROPIC_API_KEY",
    "openai": "OPENAI_API_KEY",
    "gemini": "GOOGLE_API_KEY",
}

# In-memory cache: same screenshots + same prompt version -> same answer, no new API call.
_CACHE: dict[str, list[dict]] = {}


# ---------------------------------------------------------------------------
# Validation models for the model's answer
# ---------------------------------------------------------------------------
class VisionIssue(BaseModel):
    """One issue as the vision model must return it."""

    issue_id: str
    title: str = Field(min_length=1)
    severity: Literal["high", "medium", "low"]
    evidence: str = ""
    confidence: float = Field(ge=0.0, le=1.0)
    screenshot_index: int = 0


class VisionAnswer(BaseModel):
    """The whole JSON object the vision model must return."""

    issues: list[VisionIssue]


def parse_model_output(raw_text: str) -> list[VisionIssue]:
    """
    Turn the model's raw reply into validated issues.

    Raises ModuleError(AI_BAD_OUTPUT) if the reply is not valid JSON, has the
    wrong shape, or uses an issue_id outside the allowed catalogue.
    """
    text = (raw_text or "").strip()
    if text.startswith("```"):  # remove ```json ... ``` fences if the model added them
        text = text.strip("`")
        text = text[text.find("{"):] if "{" in text else text
    try:
        answer = VisionAnswer.model_validate(json.loads(text))
    except (json.JSONDecodeError, ValidationError, TypeError) as error:
        raise ModuleError(AI_BAD_OUTPUT, f"Vision model reply was not valid: {error}") from error

    unknown = [item.issue_id for item in answer.issues if item.issue_id not in VISION_ISSUE_CATALOGUE]
    if unknown:
        raise ModuleError(AI_BAD_OUTPUT, f"Vision model used unknown issue_id(s): {unknown}")
    return answer.issues


# ---------------------------------------------------------------------------
# Choosing screenshots
# ---------------------------------------------------------------------------
def select_screenshots(scan_data: dict) -> tuple[list[str], list[str], list[str]]:
    """
    Pick cart and checkout screenshots that exist on disk.

    Returns:
        (paths, labels, warnings) - labels like "cart (desktop)" match paths by position.
    """
    paths: list[str] = []
    labels: list[str] = []
    warnings: list[str] = []
    for step in ("cart", "checkout"):
        for page in get_pages(scan_data, step):
            path = page.get("screenshot_path") or ""
            if not path or not Path(path).is_file():
                continue
            if Path(path).stat().st_size > MAX_IMAGE_BYTES:
                warnings.append(f"Screenshot too large for vision analysis, skipped: {path}")
                continue
            paths.append(path)
            labels.append(f"{step} ({page.get('viewport', 'unknown')})")
    return paths[:MAX_IMAGES], labels[:MAX_IMAGES], warnings


# ---------------------------------------------------------------------------
# Provider calls (plain HTTP)
# ---------------------------------------------------------------------------
def _b64(image: bytes) -> str:
    return base64.b64encode(image).decode("ascii")


def _post(url: str, headers: dict, body: dict) -> dict:
    """
    POST JSON and return the decoded reply, or raise AI_UNAVAILABLE.

    Busy or rate-limited replies (429, 500, 502, 503, 504) are retried after
    short waits (RETRY_WAITS_SECONDS), because they are usually temporary.
    """
    for attempt in range(len(RETRY_WAITS_SECONDS) + 1):
        try:
            response = requests.post(url, headers=headers, json=body, timeout=REQUEST_TIMEOUT_SECONDS)
        except requests.RequestException as error:
            raise ModuleError(AI_UNAVAILABLE, f"Could not reach the AI provider: {error}") from error

        if response.status_code == 200:
            return response.json()
        if response.status_code in RETRYABLE_STATUS and attempt < len(RETRY_WAITS_SECONDS):
            time.sleep(RETRY_WAITS_SECONDS[attempt])
            continue
        raise ModuleError(
            AI_UNAVAILABLE,
            f"AI provider returned HTTP {response.status_code}: {response.text[:300]}",
        )
    raise ModuleError(AI_UNAVAILABLE, "AI provider did not answer.")  # pragma: no cover


def _call_anthropic(api_key: str, model: str, system: str, prompt: str, images: list[bytes]) -> str:
    content = [
        {"type": "image", "source": {"type": "base64", "media_type": "image/png", "data": _b64(img)}}
        for img in images
    ]
    content.append({"type": "text", "text": prompt})
    data = _post(
        "https://api.anthropic.com/v1/messages",
        {"x-api-key": api_key, "anthropic-version": "2023-06-01", "content-type": "application/json"},
        {
            "model": model,
            "max_tokens": 1500,
            "temperature": 0,
            "system": system,
            "messages": [{"role": "user", "content": content}],
        },
    )
    return "".join(block.get("text", "") for block in data.get("content", []))


def _call_openai(api_key: str, model: str, system: str, prompt: str, images: list[bytes]) -> str:
    content: list[dict] = [{"type": "text", "text": prompt}]
    content += [
        {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{_b64(img)}"}}
        for img in images
    ]
    data = _post(
        "https://api.openai.com/v1/chat/completions",
        {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
        {
            "model": model,
            "temperature": 0,
            "response_format": {"type": "json_object"},
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": content},
            ],
        },
    )
    return data["choices"][0]["message"]["content"]


def _call_gemini(api_key: str, model: str, system: str, prompt: str, images: list[bytes]) -> str:
    parts: list[dict] = [{"inline_data": {"mime_type": "image/png", "data": _b64(img)}} for img in images]
    parts.append({"text": prompt})
    data = _post(
        f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent",
        {"x-goog-api-key": api_key, "Content-Type": "application/json"},
        {
            "system_instruction": {"parts": [{"text": system}]},
            "contents": [{"role": "user", "parts": parts}],
            "generationConfig": {"temperature": 0, "response_mime_type": "application/json"},
        },
    )
    try:
        return "".join(p.get("text", "") for p in data["candidates"][0]["content"]["parts"])
    except (KeyError, IndexError) as error:
        raise ModuleError(AI_BAD_OUTPUT, f"Gemini reply had no text: {str(data)[:300]}") from error


_PROVIDERS = {"anthropic": _call_anthropic, "openai": _call_openai, "gemini": _call_gemini}


def get_default_caller() -> ModelCaller:
    """
    Build a caller for the provider set in .env.

    Raises ModuleError(AI_UNAVAILABLE) if the provider is unknown or its key is missing.
    """
    provider = os.getenv("AI_PROVIDER", "anthropic").strip().lower()
    if provider not in _PROVIDERS:
        raise ModuleError(AI_UNAVAILABLE, f"Unknown AI_PROVIDER '{provider}'. Use anthropic, openai or gemini.")
    api_key = os.getenv(API_KEY_VARS[provider], "").strip()
    if not api_key or api_key.startswith("your-"):
        raise ModuleError(AI_UNAVAILABLE, f"{API_KEY_VARS[provider]} is not set in .env.")
    model = os.getenv("AI_MODEL", "").strip() or DEFAULT_MODELS[provider]
    fallback_model = os.getenv("AI_FALLBACK_MODEL", "").strip()
    provider_call = _PROVIDERS[provider]

    def call(system: str, prompt: str, images: list[bytes]) -> str:
        try:
            return provider_call(api_key, model, system, prompt, images)
        except ModuleError as error:
            # Main model busy or unavailable: try the backup model once, if one is set.
            if error.code != AI_UNAVAILABLE or not fallback_model or fallback_model == model:
                raise
            return provider_call(api_key, fallback_model, system, prompt, images)

    return call


def list_gemini_models() -> list[str]:
    """
    Return the Gemini model names this API key can use for generateContent.

    Raises ModuleError(AI_UNAVAILABLE) if the key is missing or the request fails.
    """
    api_key = os.getenv("GOOGLE_API_KEY", "").strip()
    if not api_key or api_key.startswith("your-"):
        raise ModuleError(AI_UNAVAILABLE, "GOOGLE_API_KEY is not set in .env.")
    try:
        response = requests.get(
            "https://generativelanguage.googleapis.com/v1beta/models",
            headers={"x-goog-api-key": api_key},
            params={"pageSize": 1000},
            timeout=30,
        )
    except requests.RequestException as error:
        raise ModuleError(AI_UNAVAILABLE, f"Could not reach Google: {error}") from error
    if response.status_code != 200:
        raise ModuleError(AI_UNAVAILABLE, f"Google returned HTTP {response.status_code}: {response.text[:300]}")
    return sorted(
        model["name"].removeprefix("models/")
        for model in response.json().get("models", [])
        if "generateContent" in model.get("supportedGenerationMethods", [])
    )


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------
def run_vision_checks(scan_data: dict, call_model: ModelCaller | None = None) -> tuple[list[dict], list[str]]:
    """
    Ask the vision model about the cart and checkout screenshots.

    Args:
        scan_data: ScanData from the scanner.
        call_model: Optional replacement caller (used by tests). Defaults to the
            provider configured in .env.

    Returns:
        (issues, warnings). Issues are CheckoutIssue dicts with source "vision".

    Raises:
        ModuleError(AI_UNAVAILABLE) if the model cannot be called.
        ModuleError(AI_BAD_OUTPUT) if the model answers badly twice in a row.
    """
    paths, labels, warnings = select_screenshots(scan_data)
    if not paths:
        return [], warnings  # nothing to look at: no API call, no error

    images = [Path(path).read_bytes() for path in paths]
    cache_key = PROMPT_VERSION + ":" + hashlib.sha256(b"".join(images)).hexdigest()
    if cache_key in _CACHE:
        return [dict(issue) for issue in _CACHE[cache_key]], warnings

    caller = call_model or get_default_caller()
    prompt = build_user_prompt(labels)

    try:
        parsed = parse_model_output(caller(SYSTEM_PROMPT, prompt, images))
    except ModuleError as first_error:
        if first_error.code != AI_BAD_OUTPUT:
            raise
        # One retry, telling the model what went wrong.
        parsed = parse_model_output(caller(SYSTEM_PROMPT, prompt + "\n\n" + RETRY_NOTE, images))

    issues: list[dict] = []
    seen: set[str] = set()
    for item in parsed:
        if item.issue_id in seen:
            continue
        seen.add(item.issue_id)
        category = VISION_ISSUE_CATALOGUE[item.issue_id][0]
        index = item.screenshot_index if 0 <= item.screenshot_index < len(paths) else 0
        issues.append(
            make_issue(
                item.issue_id,
                item.title,
                category,
                item.severity,
                item.evidence,
                paths[index],
                source="vision",
                confidence=round(item.confidence, 2),
            )
        )

    _CACHE[cache_key] = [dict(issue) for issue in issues]
    return issues, warnings


def clear_cache() -> None:
    """Forget cached vision answers (used by tests)."""
    _CACHE.clear()
