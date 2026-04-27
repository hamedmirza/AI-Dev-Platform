
from pathlib import Path

from app.tools.base import CommandResult
from app.tools.command_runner import run_validation_command


def run_pytest(target: str | Path = "tests") -> CommandResult:
    return run_validation_command(["pytest", str(target), "-q"])
