
from pathlib import Path

from app.tools.command_runner import run_validation_command
from app.tools.base import CommandResult


def run_ruff(target: str | Path = ".") -> CommandResult:
    return run_validation_command(["ruff", "check", str(target)])
