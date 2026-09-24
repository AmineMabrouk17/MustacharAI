"""Unified LLM client: routes chat calls to the active provider (Groq or Gemini).

The active model is switchable at runtime via ``set_active_model`` (exposed
through ``GET/POST /api/v1/models``).  Groq uses its SDK; Gemini uses the
REST ``:generateContent`` endpoint (httpx) and tolerates API-key or bearer
token authentication.
"""

from __future__ import annotations

import asyncio
import json
import os
from typing import Any

import httpx
import structlog

from mustachar.core.settings import settings
from mustachar.infra import groq_client

logger = structlog.get_logger()

# Registry of selectable chat models (used for generation and reformulation).
PROVIDERS: dict[str, dict[str, Any]] = {
    "groq": {
        "label": "Groq",
        "models": [
            "qwen/qwen3.8-27b",
            "openai/gpt-oss-120b",
            "openai/gpt-oss-20b",
            "allam-2-7b",
        ],
    },
    "gemini": {
        "label": "Gemini",
        "models": [
            "gemini-flash-latest",
            "gemini-pro-latest",
        ],
    },
    "openrouter": {
        "label": "OpenRouter",
        # Populated at import time (and on save) from the user's config file.
        "models": [],
    },
}

_ACTIVE: dict[str, str] = {
    "provider": "groq",
    "model": settings.groq_chat_model,
}

_GEMINI_BASE = "https://generativelanguage.googleapis.com/v1beta"

# Auth method that worked for Gemini (cached per process; discovered on first call).
_GEMINI_AUTH: str | None = None

# ── OpenRouter user configuration (API key + model, kept out of .env) ──────
_OPENROUTER_CONFIG_PATH = "data/openrouter_config.json"
_openrouter_config: dict[str, str] | None = None


def get_openrouter_config() -> dict[str, str]:
    """Return the saved OpenRouter ``{api_key, model}`` config (empty if unset)."""
    global _openrouter_config
    if _openrouter_config is None:
        try:
            with open(_OPENROUTER_CONFIG_PATH, encoding="utf-8") as f:
                data = json.load(f)
            _openrouter_config = (
                {
                    "api_key": str(data.get("api_key", "")),
                    "model": str(data.get("model", "")),
                }
                if isinstance(data, dict)
                else {}
            )
        except (OSError, ValueError):
            _openrouter_config = {}
    return dict(_openrouter_config)


def set_openrouter_config(api_key: str, model: str) -> dict[str, str]:
    """Persist the user's OpenRouter key/model and expose the model in the registry."""
    api_key = api_key.strip()
    model = model.strip()
    if not api_key or not model:
        raise ValueError("clé API et modèle OpenRouter requis")
    os.makedirs(os.path.dirname(_OPENROUTER_CONFIG_PATH) or ".", exist_ok=True)
    data = {"api_key": api_key, "model": model}
    with open(_OPENROUTER_CONFIG_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f)
    global _openrouter_config
    _openrouter_config = data
    if model not in PROVIDERS["openrouter"]["models"]:
        PROVIDERS["openrouter"]["models"].append(model)
    logger.info("openrouter_configured", model=model)
    return dict(data)


async def validate_openrouter_key(api_key: str) -> bool:
    """Return True if *api_key* is accepted by OpenRouter's ``/auth/key`` endpoint."""
    api_key = api_key.strip()
    if not api_key:
        return False
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.get(
                "https://openrouter.ai/api/v1/auth/key",
                headers={"Authorization": f"Bearer {api_key}"},
            )
        return resp.status_code == 200
    except httpx.HTTPError:
        return False


def get_active_model() -> dict[str, str]:
    """Return the currently active provider/model pair."""
    return dict(_ACTIVE)


def set_active_model(provider: str, model: str) -> dict[str, str]:
    """Switch the model used by ``chat``/``chat_json``.

    Raises ValueError for unknown provider/model names.  The choice is
    persisted so it survives backend restarts.
    """
    if provider not in PROVIDERS:
        raise ValueError(f"provider inconnu: {provider}")
    if model not in PROVIDERS[provider]["models"]:
        raise ValueError(f"modèle inconnu pour {provider}: {model}")
    _ACTIVE["provider"] = provider
    _ACTIVE["model"] = model
    _persist_active()
    logger.info("llm_model_active", provider=provider, model=model)
    return dict(_ACTIVE)


_ACTIVE_CONFIG_PATH = "data/active_model.json"


def _persist_active() -> None:
    """Save the active model choice across restarts (best effort)."""
    try:
        os.makedirs(os.path.dirname(_ACTIVE_CONFIG_PATH) or ".", exist_ok=True)
        with open(_ACTIVE_CONFIG_PATH, "w", encoding="utf-8") as f:
            json.dump(dict(_ACTIVE), f)
    except OSError:
        pass


def _restore_active() -> None:
    """Reload the persisted active model if it is still a known selection."""
    global _ACTIVE
    try:
        with open(_ACTIVE_CONFIG_PATH, encoding="utf-8") as f:
            data = json.load(f)
        provider = str(data.get("provider", ""))
        model = str(data.get("model", ""))
        if provider in PROVIDERS and model in PROVIDERS[provider]["models"]:
            _ACTIVE = {"provider": provider, "model": model}
            logger.info("llm_model_active", provider=provider, model=model)
    except (OSError, ValueError):
        pass


async def _gemini_chat(
    messages: list[dict[str, str]],
    *,
    temperature: float,
    max_tokens: int,
    json_mode: bool,
) -> str:
    """Call Gemini ``:generateContent`` over REST.

    503/429 (model busy / quota) are transient: the ladder retries the whole
    auth chain with backoff instead of failing immediately.  The auth method
    that first returns 200 is cached for subsequent calls.
    """
    system_parts = [m["content"] for m in messages if m["role"] == "system"]
    contents = [
        {"role": "user", "parts": [{"text": m["content"]}]}
        for m in messages
        if m["role"] != "system"
    ]

    generation_config: dict[str, Any] = {
        "temperature": temperature,
        "maxOutputTokens": max_tokens,
    }
    if json_mode:
        generation_config["responseMimeType"] = "application/json"

    body: dict[str, Any] = {"contents": contents, "generationConfig": generation_config}
    if system_parts:
        body["system_instruction"] = {"parts": [{"text": "\n".join(system_parts)}]}

    url = f"{_GEMINI_BASE}/models/{_ACTIVE['model']}:generateContent"

    global _GEMINI_AUTH
    methods = (
        ["x-goog-api-key", "query-key", "bearer"]
        if _GEMINI_AUTH is None
        else [_GEMINI_AUTH]
    )

    last_err: Exception | None = None
    async with httpx.AsyncClient(timeout=120) as client:
        for attempt in range(4):
            for auth in methods:
                target_url, headers = url, {"Content-Type": "application/json"}
                if auth == "x-goog-api-key":
                    headers["x-goog-api-key"] = settings.google_api_key
                elif auth == "query-key":
                    target_url = f"{url}?key={settings.google_api_key}"
                elif auth == "bearer":
                    headers["Authorization"] = f"Bearer {settings.google_api_key}"
                try:
                    resp = await client.post(target_url, json=body, headers=headers)
                except httpx.HTTPError as exc:
                    last_err = exc
                    continue
                if resp.status_code == 200:
                    _GEMINI_AUTH = auth
                    return _extract_gemini_text(resp.json())
                last_err = RuntimeError(
                    f"Gemini HTTP {resp.status_code}: {resp.text[:200]}"
                )
                # Busy/quota → pause and retry the chain; 4xx → next auth method.
                if resp.status_code in (429, 503):
                    break
            await asyncio.sleep(2 * (attempt + 1))
    raise last_err or RuntimeError("Gemini requête impossible")


def _extract_gemini_text(data: dict[str, Any]) -> str:
    """Extract the concatenated text parts from a Gemini generateContent reply."""
    try:
        parts = data["candidates"][0]["content"]["parts"]
        return "".join(p.get("text", "") for p in parts)
    except (KeyError, IndexError, TypeError):
        raise RuntimeError(f"Réponse Gemini inattendue: {json.dumps(data)[:300]}") from None


async def _openrouter_chat(
    messages: list[dict[str, str]],
    *,
    temperature: float,
    max_tokens: int,
    json_mode: bool,
) -> str:
    """Call the OpenRouter OpenAI-compatible endpoint with the user's own key.

    Non-streaming ``/chat/completions``; 429/503 are retried with backoff, 4xx
    errors fail fast.
    """
    cfg = get_openrouter_config()
    if not cfg.get("api_key") or not cfg.get("model"):
        raise RuntimeError("OpenRouter non configuré (clé API ou modèle manquant)")
    model = _ACTIVE["model"]
    body: dict[str, Any] = {
        "model": model,
        "messages": messages,
        "temperature": temperature,
        "max_tokens": max_tokens,
    }
    if json_mode:
        body["response_format"] = {"type": "json_object"}
    headers = {
        "Authorization": f"Bearer {cfg['api_key']}",
        "Content-Type": "application/json",
    }
    url = "https://openrouter.ai/api/v1/chat/completions"

    last_err: Exception | None = None
    async with httpx.AsyncClient(timeout=120) as client:
        for attempt in range(4):
            try:
                resp = await client.post(url, json=body, headers=headers)
            except httpx.HTTPError as exc:
                last_err = exc
                await asyncio.sleep(2 * (attempt + 1))
                continue
            if resp.status_code == 200:
                data = resp.json()
                # OpenRouter returns HTTP 200 with an error payload when the
                # upstream provider fails — surface it and retry transients.
                err = data.get("error") if isinstance(data, dict) else None
                if err:
                    code = int(err.get("code", 0) or 0)
                    message = " ".join(str(err.get("message", "")).split())[:200]
                    last_err = RuntimeError(
                        f"OpenRouter HTTP {code or 200}: {message or 'erreur inconnue'}"
                    )
                    transient = code in (429, 503) or str(
                        (err.get("metadata") or {}).get("error_type", "")
                    ) == "provider_overloaded"
                    if transient:
                        await asyncio.sleep(2 * (attempt + 1))
                        continue
                    break
                try:
                    content = data["choices"][0]["message"]["content"]
                except (KeyError, IndexError, TypeError):
                    raise RuntimeError(
                        f"Réponse OpenRouter inattendue: {resp.text[:300]}"
                    ) from None
                if not isinstance(content, str) or not content.strip():
                    return ""
                if json_mode:
                    start = content.find("{")
                    end = content.rfind("}")
                    if start != -1 and end > start:
                        return content[start : end + 1]
                return content
            last_err = RuntimeError(
                f"OpenRouter HTTP {resp.status_code}: {resp.text[:200]}"
            )
            if resp.status_code in (429, 503):
                await asyncio.sleep(2 * (attempt + 1))
                continue
            break  # auth errors: fail fast
    raise last_err or RuntimeError("OpenRouter requête impossible")


async def chat(
    messages: list[dict[str, str]],
    *,
    temperature: float = 0.3,
    max_tokens: int = 1024,
    json_mode: bool = False,
) -> str:
    """Send a chat completion through the active provider; return response text."""
    if _ACTIVE["provider"] == "groq":
        if json_mode:
            return await groq_client.chat_json(
                messages,
                model=_ACTIVE["model"],
                temperature=temperature,
                max_tokens=max_tokens,
            )
        return await groq_client.chat(
            messages,
            model=_ACTIVE["model"],
            temperature=temperature,
            max_tokens=max_tokens,
        )
    if _ACTIVE["provider"] == "openrouter":
        return await _openrouter_chat(
            messages,
            temperature=temperature,
            max_tokens=max_tokens,
            json_mode=json_mode,
        )
    return await _gemini_chat(
        messages,
        temperature=temperature,
        max_tokens=max_tokens,
        json_mode=json_mode,
    )


async def chat_json(
    messages: list[dict[str, str]],
    *,
    temperature: float = 0.3,
    max_tokens: int = 600,
) -> str:
    """Send a chat completion and return the JSON string from the response."""
    return await chat(
        messages,
        temperature=temperature,
        max_tokens=max_tokens,
        json_mode=True,
    )


# Expose a previously saved OpenRouter model in the selectable registry, then
# restore the last active model choice (survives backend restarts).
_or_cfg = get_openrouter_config()
if _or_cfg.get("model"):
    PROVIDERS["openrouter"]["models"] = [_or_cfg["model"]]
_restore_active()
