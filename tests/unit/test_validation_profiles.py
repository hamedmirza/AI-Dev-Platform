from pathlib import Path

import pytest

from app.core.exceptions import ConfigurationError
from app.tools.command_runner import (
    detect_validation_profile,
    ensure_command_allowed_for_profile,
    validation_commands_for_profile,
)


def _write_vite_package(root: Path) -> None:
    frontend = root / "frontend"
    frontend.mkdir()
    package_json = (
        '{"scripts":{"build":"vite build","test":"vitest run"},'
        '"devDependencies":{"vite":"latest"}}'
    )
    (frontend / "package.json").write_text(
        package_json,
        encoding="utf-8",
    )
    (frontend / "package-lock.json").write_text("{}", encoding="utf-8")


def test_python_profile_allows_only_python_commands(tmp_path: Path) -> None:
    (tmp_path / "app").mkdir()
    (tmp_path / "tests").mkdir()

    commands = [spec.command for spec in validation_commands_for_profile("python", tmp_path)]

    assert commands == [["ruff", "check", "app", "tests"], ["mypy", "app"], ["pytest", "-q"]]
    with pytest.raises(ConfigurationError):
        ensure_command_allowed_for_profile(
            "python",
            ["npm", "--prefix", "frontend", "run", "build"],
            tmp_path,
        )


def test_react_vite_profile_uses_frontend_commands_only(tmp_path: Path) -> None:
    _write_vite_package(tmp_path)

    commands = [spec.command for spec in validation_commands_for_profile("react-vite", tmp_path)]

    assert commands == [
        ["npm", "--prefix", "frontend", "ci"],
        ["npm", "--prefix", "frontend", "run", "build"],
        ["npm", "--prefix", "frontend", "run", "test"],
    ]
    assert ["ruff", "check", "app", "tests"] not in commands


def test_full_stack_profile_runs_python_then_frontend(tmp_path: Path) -> None:
    (tmp_path / "app").mkdir()
    (tmp_path / "tests").mkdir()
    _write_vite_package(tmp_path)

    commands = [spec.command for spec in validation_commands_for_profile("full-stack", tmp_path)]

    assert commands[:3] == [["ruff", "check", "app", "tests"], ["mypy", "app"], ["pytest", "-q"]]
    assert commands[3:] == [
        ["npm", "--prefix", "frontend", "ci"],
        ["npm", "--prefix", "frontend", "run", "build"],
        ["npm", "--prefix", "frontend", "run", "test"],
    ]


def test_frontend_target_auto_detects_react_vite(tmp_path: Path) -> None:
    (tmp_path / "app").mkdir()
    (tmp_path / "tests").mkdir()
    _write_vite_package(tmp_path)

    profile = detect_validation_profile(tmp_path, target_files=["frontend/src/main.tsx"])
    assert profile == "react-vite"


def test_backend_ai_trader_python_profile_sets_pythonpath(tmp_path: Path) -> None:
    (tmp_path / "backend" / "ai_trader").mkdir(parents=True)

    specs = validation_commands_for_profile("python", tmp_path)

    assert [spec.command for spec in specs] == [
        ["ruff", "check", "backend"],
        ["mypy", "backend"],
        ["pytest", "-q"],
    ]
    assert all(spec.env == {"PYTHONPATH": "backend"} for spec in specs)


def test_custom_profile_uses_explicit_allowlisted_commands(tmp_path: Path) -> None:
    specs = validation_commands_for_profile(
        "custom",
        tmp_path,
        custom_commands=[["pytest", "-q"]],
    )

    assert [spec.command for spec in specs] == [["pytest", "-q"]]
