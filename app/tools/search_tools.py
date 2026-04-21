
import subprocess
from pathlib import Path


def search_workspace(pattern: str, root: str | Path = ".") -> list[str]:
    proc = subprocess.run(
        ["rg", "-n", pattern, str(root)],
        text=True,
        capture_output=True,
        check=False,
    )
    if proc.returncode not in {0, 1}:
        raise RuntimeError(proc.stderr.strip() or "Search failed.")
    return [line for line in proc.stdout.splitlines() if line.strip()]
