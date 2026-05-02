"""Validate per-task clone sources (local path or git remote) against operator policy."""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Literal, Optional
from urllib.parse import urlparse

from app.core.exceptions import ConfigurationError
from app.core.settings import Settings


@dataclass(frozen=True)
class ResolvedSource:
    kind: Literal["local", "remote"]
    local_path: Optional[Path] = None
    remote_url: Optional[str] = None


_MAX_SPEC_LEN = 2048
_SHELLISH = re.compile(r"[`$;|&<>()\n\r\0]")


def _parse_allowed_hosts(settings: Settings) -> list[str]:
    raw = (settings.allowed_git_hosts or "").strip()
    if not raw:
        return []
    return [h.strip().lower() for h in raw.split(",") if h.strip()]


def _parse_allowed_roots(settings: Settings) -> list[Path]:
    raw = (settings.allowed_source_repo_roots or "").strip()
    if not raw:
        return []
    return [Path(p.strip()).resolve() for p in raw.split(",") if p.strip()]


def validate_source_repo_spec(spec: str | None, settings: Settings) -> ResolvedSource:
    """
    Validate a task-level source_repo_spec string.
    Remote URLs require a non-empty allowed_git_hosts allowlist entry for the host.
    Local paths must exist, contain .git, and (if roots configured) sit under an allowed root.
    """
    if spec is None or not str(spec).strip():
        raise ConfigurationError("source_repo_spec is empty.")

    s = str(spec).strip()
    if len(s) > _MAX_SPEC_LEN:
        raise ConfigurationError("source_repo_spec exceeds maximum length.")
    if _SHELLISH.search(s):
        raise ConfigurationError("source_repo_spec contains disallowed characters.")

    lowered = s.lower()
    if lowered.startswith("file://"):
        raise ConfigurationError("file:// URLs are not allowed for source_repo.")

    is_remote = lowered.startswith(("https://", "http://", "git@", "ssh://"))
    if is_remote:
        return _validate_remote(s, settings)
    return _validate_local(s, settings)


def _validate_remote(url: str, settings: Settings) -> ResolvedSource:
    allowed = _parse_allowed_hosts(settings)
    if not allowed:
        raise ConfigurationError(
            "Remote source_repo is disabled until ALLOWED_GIT_HOSTS is set "
            "(comma-separated hostnames, e.g. github.com)."
        )

    if url.startswith("git@"):
        # git@host:org/repo.git
        host_part = url.split("@", 1)[1]
        host = host_part.split(":", 1)[0].strip().lower()
    elif url.startswith("ssh://"):
        parsed = urlparse(url)
        host = (parsed.hostname or "").lower()
    else:
        parsed = urlparse(url)
        host = (parsed.hostname or "").lower()

    if not host:
        raise ConfigurationError("Could not determine host from remote URL.")
    if host in {"localhost", "127.0.0.1", "::1"}:
        raise ConfigurationError("Loopback hosts are not allowed for remote source_repo.")
    if host not in allowed and host.rstrip(".") not in allowed:
        raise ConfigurationError(
            f"Host {host!r} is not in ALLOWED_GIT_HOSTS.",
        )

    return ResolvedSource(kind="remote", remote_url=url)


def _validate_local(path_str: str, settings: Settings) -> ResolvedSource:
    path = Path(path_str).expanduser().resolve()
    if ".." in Path(path_str).parts:
        raise ConfigurationError("source_repo path must not contain '..'.")

    roots = _parse_allowed_roots(settings)
    if roots:
        if not any(str(path).startswith(str(r) + "/") or path == r for r in roots):
            raise ConfigurationError(
                "Local source_repo is outside ALLOWED_SOURCE_REPO_ROOTS.",
            )

    if not path.exists():
        raise ConfigurationError(f"Local source_repo does not exist: {path}")
    if not path.is_dir():
        raise ConfigurationError(f"Local source_repo is not a directory: {path}")
    if not (path / ".git").exists():
        raise ConfigurationError(f"Local source_repo is not a git checkout: {path}")

    return ResolvedSource(kind="local", local_path=path)


def repo_key_for_source_spec(source_repo_spec: str | None) -> str:
    """Stable scope key for lessons/playbooks (not cryptographic secrecy)."""
    if not source_repo_spec or not str(source_repo_spec).strip():
        return "global"
    normalized = str(source_repo_spec).strip()
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()[:24]
