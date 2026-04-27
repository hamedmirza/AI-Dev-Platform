from __future__ import annotations

import subprocess
from pathlib import Path

from app.core.exceptions import ConfigurationError
from app.tools.base import CommandResult

ALLOWED_VALIDATION_COMMANDS = {
    ("pytest",),
    ("ruff", "check"),
    ("ruff", "format", "--check"),
    ("mypy",),
}


def run_validation_command(
    command: list[str],
    cwd: str | Path = ".",
    timeout_seconds: float = 60.0,
) -> CommandResult:
    if not _is_allowed_command(command):
        raise ConfigurationError(f"Validation command is not allowed: {' '.join(command)}")

    try:
        proc = subprocess.run(
            command,
            cwd=str(cwd),
            text=True,
            capture_output=True,
            check=False,
            timeout=timeout_seconds,
        )
        return CommandResult(
            command=command,
            returncode=proc.returncode,
            stdout=proc.stdout,
            stderr=proc.stderr,
        )
    except subprocess.TimeoutExpired as exc:
        return CommandResult(
            command=command,
            returncode=124,
            stdout=_normalize_output(exc.stdout),
            stderr=_normalize_output(
                exc.stderr or f"Command timed out after {timeout_seconds} seconds."
            ),
            timed_out=True,
        )


def _is_allowed_command(command: list[str]) -> bool:
    return any(command[: len(prefix)] == list(prefix) for prefix in ALLOWED_VALIDATION_COMMANDS)


def _normalize_output(value: bytes | str | None) -> str:
    if value is None:
        return ""
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    return value
