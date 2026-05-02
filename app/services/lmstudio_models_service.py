"""List models from LM Studio OpenAI-compatible API."""

from __future__ import annotations

from typing import Any

import httpx

from app.core.settings import Settings


def fetch_lmstudio_models(settings: Settings) -> tuple[list[dict[str, str]], str | None]:
    base = settings.lmstudio_base_url.rstrip("/")
    url = f"{base}/models"
    headers = {"Authorization": f"Bearer {settings.lmstudio_api_key}"}
    try:
        with httpx.Client(timeout=min(15.0, settings.provider_timeout_seconds)) as client:
            response = client.get(url, headers=headers)
    except Exception as exc:  # pragma: no cover - network
        return [], str(exc)
    if response.status_code != 200:
        return [], f"HTTP {response.status_code}: {response.text[:500]}"
    try:
        payload: dict[str, Any] = response.json()
    except Exception as exc:
        return [], f"Invalid JSON: {exc}"
    data = payload.get("data")
    if not isinstance(data, list):
        return [], "Unexpected /models response shape."
    models: list[dict[str, str]] = []
    for item in data:
        if isinstance(item, dict):
            mid = item.get("id")
            if isinstance(mid, str) and mid.strip():
                models.append({"id": mid.strip()})
    return models, None
