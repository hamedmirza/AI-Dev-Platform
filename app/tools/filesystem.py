
import shutil
from pathlib import Path

from app.core.exceptions import ConfigurationError
from app.core.settings import get_settings
from app.tools.workspace_guard import ensure_within_root


def ensure_directory(path: Path) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    return path


def prepare_workspace_directory(run_id: str) -> Path:
    settings = get_settings()
    root = ensure_directory(settings.workspace_root_path)
    workspace = root / f"run-{run_id}"
    if workspace.exists():
        shutil.rmtree(workspace)
    workspace.mkdir(parents=True, exist_ok=False)
    return ensure_within_root(workspace, root)


def require_source_repo() -> Path:
    settings = get_settings()
    repo_path = settings.source_repo_path_resolved
    if repo_path is None:
        raise ConfigurationError("No source repository path is configured.")
    if not repo_path.exists():
        raise ConfigurationError(f"Configured source repository does not exist: {repo_path}")
    if not (repo_path / ".git").exists():
        raise ConfigurationError(f"Configured source repository is not a git checkout: {repo_path}")
    return repo_path


def list_text_files(root: Path) -> list[str]:
    if not root.exists():
        return []
    files = [
        str(path.relative_to(root))
        for path in root.rglob("*")
        if path.is_file() and ".git" not in path.parts
    ]
    return sorted(files)


def read_text_file(root: Path, relative_path: str) -> str:
    path = ensure_within_root(root / relative_path, root)
    if not path.exists() or not path.is_file():
        raise ConfigurationError(f"File does not exist: {relative_path}")
    return path.read_text(encoding="utf-8")


def write_text_file(root: Path, relative_path: str, content: str) -> Path:
    path = ensure_within_root(root / relative_path, root)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return path
