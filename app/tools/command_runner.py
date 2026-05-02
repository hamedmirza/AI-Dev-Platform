from __future__ import annotations

import subprocess
from pathlib import Path

from app.core.exceptions import ConfigurationError
from app.tools.base import CommandResult

ALLOWED_VALIDATION_COMMANDS = {
    ("ruff", "check", "."),
    ("mypy", "app"),
    ("pytest", "-q"),
    ("pytest", "tests", "-q"),
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
    except FileNotFoundError as exc:
        return CommandResult(
            command=command,
            returncode=127,
            stdout="",
            stderr=str(exc),
        )


def _is_allowed_command(command: list[str]) -> bool:
    if tuple(command) in ALLOWED_VALIDATION_COMMANDS:
        return True
    return (
        len(command) == 3
        and command[0] == "pytest"
        and command[2] == "-q"
        and not command[1].startswith("-")
    )


def _normalize_output(value: bytes | str | None) -> str:
    if value is None:
        return ""
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    return value
