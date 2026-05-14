import json

import httpx

from app.providers.lmstudio import _lmstudio_response_detail


def test_lmstudio_response_detail_openai_style() -> None:
    r = httpx.Response(
        400,
        content=json.dumps({"error": {"message": "No such model: foo"}}).encode(),
    )
    assert "No such model" in _lmstudio_response_detail(r)


def test_lmstudio_response_detail_plain_text() -> None:
    r = httpx.Response(400, content=b"bad request")
    assert _lmstudio_response_detail(r) == "bad request"
