
from pathlib import Path

from app.tools.base import CommandResult
from app.tools.command_runner import run_validation_command


def run_ruff(target: str | Path = ".") -> CommandResult:
    return run_validation_command(["ruff", "check", str(target)])
