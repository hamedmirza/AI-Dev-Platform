import os
from typing import Optional, cast

import httpx

from app.core.settings import Settings, get_settings


def get_github_token() -> Optional[str]:
    for key in ("GITHUB_TOKEN", "GITHUB_PAT", "GH_TOKEN"):
        value = os.getenv(key)
        if value:
            return value
    return None


def github_repo_metadata(settings: Settings) -> dict[str, str]:
    """Resolved URLs for the configured canonical GitHub repository (operator metadata)."""
    full = (settings.github_repo_full_name or "").strip()
    branch = (settings.github_repo_default_branch or "main").strip() or "main"
    if not full or "/" not in full:
        return {
            "repo_full_name": "",
            "repo_html_url": "",
            "repo_clone_url": "",
            "repo_default_branch": branch,
        }
    parts = [p for p in full.split("/") if p]
    owner_repo = "/".join(parts[:2]) if len(parts) >= 2 else ""
    if not owner_repo:
        return {
            "repo_full_name": "",
            "repo_html_url": "",
            "repo_clone_url": "",
            "repo_default_branch": branch,
        }
    base = f"https://github.com/{owner_repo}"
    return {
        "repo_full_name": owner_repo,
        "repo_html_url": base,
        "repo_clone_url": f"{base}.git",
        "repo_default_branch": branch,
    }


def get_github_status() -> dict[str, object]:
    settings = get_settings()
    meta: dict[str, object] = cast(dict[str, object], github_repo_metadata(settings))
    token = get_github_token()
    if not token:
        return {
            **meta,
            "configured": False,
            "detail": "No GitHub API token is configured in GITHUB_TOKEN, GITHUB_PAT, or GH_TOKEN.",
        }

    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
        "User-Agent": "ai-dev-platform",
    }
    try:
        with httpx.Client(timeout=min(settings.provider_timeout_seconds, 10.0)) as client:
            response = client.get("https://api.github.com/user", headers=headers)
            response.raise_for_status()
        data = response.json()
        return {
            **meta,
            "configured": True,
            "detail": "GitHub API token is valid.",
            "login": data.get("login"),
        }
    except httpx.HTTPError as exc:
        return {
            **meta,
            "configured": False,
            "detail": f"GitHub API validation failed: {exc}",
        }
