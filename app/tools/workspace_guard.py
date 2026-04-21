
from pathlib import Path

from app.core.exceptions import ConfigurationError


def ensure_within_root(path: Path, root: Path) -> Path:
    resolved_path = path.resolve()
    resolved_root = root.resolve()

    if resolved_path == resolved_root or resolved_root in resolved_path.parents:
        return resolved_path

    raise ConfigurationError(
        f"Path '{resolved_path}' is outside the allowed root '{resolved_root}'.",
    )
