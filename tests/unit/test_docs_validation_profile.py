"""Tests for the docs-only validation profile narrowing.

The M1 smoke run revealed that a docs-only `target_files=['README.md']` task was getting the
heavy ``full-stack`` profile because the auto-detection only narrowed for ``frontend/``,
``app/``, ``backend/``, or ``tests/`` prefixes. This led to cascading reviewer rejections
unrelated to the actual change. The fix adds a ``docs`` profile that runs no automated
commands when every target file is a documentation file.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from app.core.exceptions import ConfigurationError
from app.tools.command_runner import (
    VALIDATION_PROFILES,
    available_validation_profiles,
    detect_validation_profile,
    validation_commands_for_profile,
)


@pytest.fixture
def full_stack_repo(tmp_path: Path) -> Path:
    """Repo with both python app/ and frontend/ to force full-stack auto-detection."""
    (tmp_path / "app").mkdir()
    (tmp_path / "app" / "main.py").write_text("# main\n", encoding="utf-8")
    (tmp_path / "frontend").mkdir()
    (tmp_path / "frontend" / "package.json").write_text(
        '{"scripts": {"build": "vite build", "dev": "vite"}}\n',
        encoding="utf-8",
    )
    (tmp_path / "frontend" / "vite.config.ts").write_text("// vite\n", encoding="utf-8")
    return tmp_path


def test_docs_profile_registered() -> None:
    assert "docs" in VALIDATION_PROFILES
    assert "docs" in available_validation_profiles()


def test_docs_profile_has_no_commands(tmp_path: Path) -> None:
    assert validation_commands_for_profile("docs", tmp_path) == []


def test_markdown_only_target_resolves_to_docs(full_stack_repo: Path) -> None:
    assert (
        detect_validation_profile(full_stack_repo, target_files=["README.md"])
        == "docs"
    )


def test_docs_directory_target_resolves_to_docs(full_stack_repo: Path) -> None:
    assert (
        detect_validation_profile(
            full_stack_repo,
            target_files=["docs/ARCHITECTURE.md", "docs/RUNBOOK.md"],
        )
        == "docs"
    )


def test_mixed_docs_and_code_does_not_resolve_to_docs(full_stack_repo: Path) -> None:
    # If any target is non-docs, we must not use the docs profile.
    profile = detect_validation_profile(
        full_stack_repo,
        target_files=["README.md", "app/main.py"],
    )
    assert profile != "docs"
    assert profile in {"python", "full-stack"}


def test_full_stack_unchanged_when_no_targets(full_stack_repo: Path) -> None:
    assert detect_validation_profile(full_stack_repo, target_files=None) == "full-stack"


def test_unknown_profile_still_raises(tmp_path: Path) -> None:
    with pytest.raises(ConfigurationError):
        validation_commands_for_profile("does-not-exist", tmp_path)
