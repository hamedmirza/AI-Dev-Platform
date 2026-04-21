import os
from typing import Optional

import httpx

from app.core.settings import get_settings


def get_github_token() -> Optional[str]:
    for key in ("GITHUB_TOKEN", "GITHUB_PAT", "GH_TOKEN"):
        value = os.getenv(key)
        if value:
            return value
    return None


def get_github_status() -> dict[str, object]:
    token = get_github_token()
    if not token:
        return {
            "configured": False,
            "detail": "No GitHub API token is configured in GITHUB_TOKEN, GITHUB_PAT, or GH_TOKEN.",
        }

    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
        "User-Agent": "ai-dev-platform",
    }
    try:
        with httpx.Client(timeout=min(get_settings().provider_timeout_seconds, 10.0)) as client:
            response = client.get("https://api.github.com/user", headers=headers)
            response.raise_for_status()
        data = response.json()
        return {
            "configured": True,
            "detail": "GitHub API token is valid.",
            "login": data.get("login"),
        }
    except httpx.HTTPError as exc:
        return {
            "configured": False,
            "detail": f"GitHub API validation failed: {exc}",
        }
