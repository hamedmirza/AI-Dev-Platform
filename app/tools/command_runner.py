from __future__ import annotations

import json
import os
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

from app.core.exceptions import ConfigurationError
from app.tools.base import CommandResult

VALIDATION_PROFILES = {"python", "react-vite", "full-stack", "docs", "custom"}

# File extensions / path prefixes that mean "this change is documentation only".
_DOCS_EXTENSIONS = {".md", ".rst", ".txt", ".adoc"}
_DOCS_PATH_PREFIXES = ("docs/", "doc/")


def _is_docs_target(target: str) -> bool:
    lowered = target.lower()
    if any(lowered.startswith(prefix) for prefix in _DOCS_PATH_PREFIXES):
        return True
    suffix = "." + lowered.rsplit(".", 1)[-1] if "." in lowered else ""
    return suffix in _DOCS_EXTENSIONS


@dataclass(frozen=True)
class ValidationCommandSpec:
    command: list[str]
    env: dict[str, str] = field(default_factory=dict)


def resolve_validation_profile(
    workspace_path: str | Path,
    *,
    task_profile: str | None = None,
    project_profile: str | None = None,
    target_files: list[str] | None = None,
) -> str:
    for profile in (task_profile, project_profile):
        normalized = _normalize_profile(profile)
        if normalized and normalized != "auto":
            return normalized
    return detect_validation_profile(workspace_path, target_files=target_files)


def detect_validation_profile(
    workspace_path: str | Path,
    *,
    target_files: list[str] | None = None,
) -> str:
    root = Path(workspace_path)
    has_frontend = _has_vite_frontend(root)
    has_python = _has_python_app(root)
    normalized_targets = [item.strip().strip("/") for item in target_files or [] if item.strip()]

    if normalized_targets:
        docs_target = all(_is_docs_target(item) for item in normalized_targets)
        if docs_target:
            return "docs"
        frontend_target = all(
            item == "frontend" or item.startswith("frontend/") for item in normalized_targets
        )
        python_target = all(
            item == "app"
            or item.startswith("app/")
            or item == "backend"
            or item.startswith("backend/")
            or item == "tests"
            or item.startswith("tests/")
            for item in normalized_targets
        )
        if frontend_target and has_frontend:
            return "react-vite"
        if python_target and has_python:
            return "python"

    if has_frontend and has_python:
        return "full-stack"
    if has_frontend:
        return "react-vite"
    return "python"


def validation_commands_for_profile(
    profile: str,
    workspace_path: str | Path,
    *,
    custom_commands: list[list[str]] | None = None,
) -> list[ValidationCommandSpec]:
    normalized = _normalize_profile(profile) or "python"
    root = Path(workspace_path)
    if normalized == "custom":
        return [ValidationCommandSpec(command=command) for command in custom_commands or []]
    if normalized == "python":
        return _python_validation_commands(root)
    if normalized == "react-vite":
        return _react_vite_validation_commands(root)
    if normalized == "full-stack":
        return [*_python_validation_commands(root), *_react_vite_validation_commands(root)]
    if normalized == "docs":
        # Documentation-only changes intentionally run no automated commands;
        # the patch guard + reviewer still verify scope and well-formedness.
        return []
    raise ConfigurationError(f"Unknown validation profile: {profile}")


def ensure_command_allowed_for_profile(
    profile: str,
    command: list[str],
    workspace_path: str | Path,
) -> None:
    allowed = {
        tuple(spec.command) for spec in validation_commands_for_profile(profile, workspace_path)
    }
    if tuple(command) not in allowed:
        raise ConfigurationError(
            f"Validation command is not allowed for {profile} profile: {' '.join(command)}"
        )


def available_validation_profiles() -> dict[str, list[str]]:
    return {
        "python": ["ruff check app tests", "mypy app", "pytest -q"],
        "react-vite": [
            "npm --prefix frontend ci",
            "npm --prefix frontend run build",
            "npm --prefix frontend run test",
        ],
        "full-stack": [
            "ruff check app tests",
            "mypy app",
            "pytest -q",
            "npm --prefix frontend ci",
            "npm --prefix frontend run build",
            "npm --prefix frontend run test",
        ],
        "docs": [
            "(no commands; documentation-only changes skip automated validation)",
        ],
        "custom": ["Explicit allowlisted commands from project/task configuration"],
    }


def run_validation_command(
    command: list[str],
    cwd: str | Path = ".",
    timeout_seconds: float = 60.0,
    env: dict[str, str] | None = None,
) -> CommandResult:
    if not _is_allowed_command(command):
        raise ConfigurationError(f"Validation command is not allowed: {' '.join(command)}")

    try:
        effective_timeout = _timeout_for_command(command, timeout_seconds)
        process_env = os.environ.copy()
        if env:
            process_env.update(env)
        proc = subprocess.run(
            command,
            cwd=str(cwd),
            env=process_env,
            text=True,
            capture_output=True,
            check=False,
            timeout=effective_timeout,
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


def _timeout_for_command(command: list[str], default_timeout: float) -> float:
    if command == ["npm", "ci"] or command == ["npm", "--prefix", "frontend", "ci"]:
        return 300.0
    if command[:2] == ["npm", "run"] or command[:3] == ["npm", "--prefix", "frontend"]:
        return 180.0
    return default_timeout


def _is_allowed_command(command: list[str]) -> bool:
    if tuple(command) in _allowed_validation_commands():
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


def _normalize_profile(value: str | None) -> str | None:
    if value is None:
        return None
    profile = value.strip().lower()
    if profile in {"", "default"}:
        return None
    if profile not in {*VALIDATION_PROFILES, "auto"}:
        raise ConfigurationError(f"Unknown validation profile: {value}")
    return profile


def _has_vite_frontend(root: Path) -> bool:
    package_path = root / "frontend" / "package.json"
    if not package_path.exists():
        return False
    try:
        package = json.loads(package_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError):
        return False
    scripts = package.get("scripts")
    deps = {**package.get("dependencies", {}), **package.get("devDependencies", {})}
    if isinstance(scripts, dict) and any("vite" in str(value) for value in scripts.values()):
        return True
    return "vite" in deps


def _has_python_app(root: Path) -> bool:
    return (
        (root / "pyproject.toml").exists()
        or (root / "app").exists()
        or (root / "tests").exists()
        or (root / "backend" / "ai_trader").exists()
    )


def _python_validation_commands(root: Path) -> list[ValidationCommandSpec]:
    env: dict[str, str] = {}
    if (root / "backend" / "ai_trader").exists():
        env["PYTHONPATH"] = "backend"
    if (root / "app").exists():
        lint_targets = ["app"]
        if (root / "tests").exists():
            lint_targets.append("tests")
        type_target = "app"
    elif (root / "backend").exists():
        lint_targets = ["backend"]
        type_target = "backend"
    elif (root / "tests").exists():
        lint_targets = ["tests"]
        type_target = None
    else:
        lint_targets = ["."]
        type_target = None
    commands = [ValidationCommandSpec(["ruff", "check", *lint_targets], env=env)]
    if type_target is not None:
        commands.append(ValidationCommandSpec(["mypy", type_target], env=env))
    commands.append(ValidationCommandSpec(["pytest", "-q"], env=env))
    return commands


def _react_vite_validation_commands(root: Path) -> list[ValidationCommandSpec]:
    package_lock = root / "frontend" / "package-lock.json"
    commands: list[ValidationCommandSpec] = []
    if package_lock.exists():
        commands.append(ValidationCommandSpec(["npm", "--prefix", "frontend", "ci"]))
    commands.extend(
        [
            ValidationCommandSpec(["npm", "--prefix", "frontend", "run", "build"]),
            ValidationCommandSpec(["npm", "--prefix", "frontend", "run", "test"]),
        ]
    )
    return commands


def _allowed_validation_commands() -> set[tuple[str, ...]]:
    return {
        ("npm", "ci"),
        ("npm", "run", "lint"),
        ("npm", "run", "test"),
        ("npm", "run", "typecheck"),
        ("npm", "run", "build"),
        ("npm", "--prefix", "frontend", "ci"),
        ("npm", "--prefix", "frontend", "run", "lint"),
        ("npm", "--prefix", "frontend", "run", "test"),
        ("npm", "--prefix", "frontend", "run", "typecheck"),
        ("npm", "--prefix", "frontend", "run", "build"),
        ("ruff", "check", "."),
        ("ruff", "check", "app", "tests"),
        ("ruff", "check", "backend"),
        ("ruff", "check", "tests"),
        ("mypy", "app"),
        ("mypy", "backend"),
        ("mypy", "tests"),
        ("mypy", "."),
        ("pytest", "-q"),
        ("pytest", "tests", "-q"),
    }
