
from pathlib import Path

from app.tools.command_runner import run_validation_command
from app.tools.base import CommandResult


def run_pytest(target: str | Path = "tests") -> CommandResult:
    return run_validation_command(["pytest", str(target), "-q"])
