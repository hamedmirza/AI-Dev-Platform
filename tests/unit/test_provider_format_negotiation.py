"""Tests for LM Studio provider response_format negotiation and caching.

After the M1 smoke surfaced repeated 400 'response_format.type must be json_schema or text'
warnings from LM Studio, the provider now:
- Sends json_schema as the primary format (LM Studio's native shape).
- Caches the working response_format mode on the provider instance after the first 400, so
  every subsequent call is correct on the first try.
"""

from __future__ import annotations

from typing import Any

import httpx
import pytest

from app.core.settings import Settings, clear_settings_cache
from app.providers.lmstudio import LMStudioProvider


@pytest.fixture
def lm_settings(monkeypatch: pytest.MonkeyPatch) -> Settings:
    monkeypatch.setenv("LMSTUDIO_BASE_URL", "http://lmstudio.test/v1")
    monkeypatch.setenv("LMSTUDIO_MODEL", "fake-model")
    monkeypatch.setenv("LMSTUDIO_API_KEY", "k")
    clear_settings_cache()
    return Settings()


def _patch_client(provider: LMStudioProvider, handler) -> list[dict[str, Any]]:
    import json

    posts: list[dict[str, Any]] = []

    def _transport(request: httpx.Request) -> httpx.Response:
        raw = request.content or b""
        try:
            decoded = json.loads(raw.decode("utf-8")) if raw else {}
        except (json.JSONDecodeError, UnicodeDecodeError):
            decoded = {}
        posts.append(decoded)
        return handler(request, decoded)

    provider._client = httpx.Client(transport=httpx.MockTransport(_transport))
    return posts


def _ok_response() -> httpx.Response:
    return httpx.Response(
        200,
        json={"choices": [{"message": {"content": '{"ok": true}'}}]},
    )


def _reject_response_format(detail: str) -> httpx.Response:
    return httpx.Response(400, json={"error": {"message": detail}})


def test_first_call_sends_json_schema_response_format(lm_settings: Settings) -> None:
    provider = LMStudioProvider(lm_settings)
    posts = _patch_client(provider, lambda req, body: _ok_response())

    provider.invoke_json("sys", "user")
    assert len(posts) == 1
    rf = posts[0].get("response_format")
    assert rf == {
        "type": "json_schema",
        "json_schema": {
            "name": "agent_response",
            "strict": False,
            "schema": {"type": "object", "additionalProperties": True},
        },
    }


def test_negotiation_caches_after_400_then_skips_retry(lm_settings: Settings) -> None:
    provider = LMStudioProvider(lm_settings)
    call_count = {"n": 0}

    def handler(req: httpx.Request, body: dict[str, Any]) -> httpx.Response:
        call_count["n"] += 1
        rf = body.get("response_format")
        # Reject anything that uses json_schema; accept text or no format.
        if isinstance(rf, dict) and rf.get("type") == "json_schema":
            return _reject_response_format(
                "'response_format.type' must be 'json_schema' or 'text'"
            )
        return _ok_response()

    posts = _patch_client(provider, handler)

    # First call should: try json_schema (400) -> downgrade to text (200). Two requests total.
    provider.invoke_json("sys", "user")
    assert len(posts) == 2
    assert posts[0]["response_format"]["type"] == "json_schema"
    assert posts[1]["response_format"]["type"] == "text"

    # Second call must skip json_schema entirely (cached) and go straight to text.
    provider.invoke_json("sys", "another")
    assert len(posts) == 3
    assert posts[2]["response_format"]["type"] == "text"


def test_negotiation_drops_response_format_when_both_rejected(lm_settings: Settings) -> None:
    provider = LMStudioProvider(lm_settings)

    def handler(req: httpx.Request, body: dict[str, Any]) -> httpx.Response:
        rf = body.get("response_format")
        # Reject any response_format whatsoever.
        if rf:
            return _reject_response_format("response_format not supported by this build")
        return _ok_response()

    posts = _patch_client(provider, handler)

    provider.invoke_json("sys", "user")
    # Expected sequence: json_schema (400) -> text (400) -> no response_format (200).
    assert len(posts) == 3
    assert posts[0]["response_format"]["type"] == "json_schema"
    assert posts[1]["response_format"]["type"] == "text"
    assert "response_format" not in posts[2]
    # Subsequent calls now skip response_format on the first try.
    provider.invoke_json("sys", "again")
    assert len(posts) == 4
    assert "response_format" not in posts[3]
