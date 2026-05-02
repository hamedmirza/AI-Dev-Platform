import shutil
from pathlib import Path
from typing import TYPE_CHECKING, Optional, cast

from app.core.exceptions import ConfigurationError
from app.core.settings import get_settings
from app.tools.filesystem import (
    list_text_files,
    prepare_workspace_directory,
    read_text_file,
    require_source_repo,
    write_text_file,
)
from app.tools.git_tools import (
    checkout_new_branch,
    clone_local_repository,
    clone_remote_repository,
    commit_all_changes,
    current_branch,
    current_head_sha,
    get_workspace_diff,
    list_workspace_files,
    validate_git_repository,
)
from app.tools.workspace_guard import ensure_within_root

if TYPE_CHECKING:
    from app.db.models import TaskModel


def get_repository_summary() -> dict[str, object]:
    repo_path = require_source_repo()
    summary = validate_git_repository(repo_path)
    summary["head_sha"] = current_head_sha(repo_path)
    return summary


def create_run_workspace(run_id: str, task: Optional["TaskModel"] = None) -> Path:
    from app.services.source_repo_policy import validate_source_repo_spec

    settings = get_settings()
    workspace_path = prepare_workspace_directory(run_id)
    spec = (task.source_repo_spec.strip() if task and task.source_repo_spec else "") or ""

    if spec:
        resolved = validate_source_repo_spec(spec, settings)
        if resolved.kind == "local" and resolved.local_path is not None:
            clone_local_repository(resolved.local_path, workspace_path)
        elif resolved.kind == "remote" and resolved.remote_url is not None:
            clone_remote_repository(
                resolved.remote_url,
                workspace_path,
                timeout_seconds=settings.git_clone_timeout_seconds,
                depth=1,
            )
        else:
            raise ConfigurationError("Invalid resolved source repository.")
    else:
        repo_path = require_source_repo()
        clone_local_repository(repo_path, workspace_path)

    checkout_new_branch(workspace_path, f"run/{run_id}")
    return workspace_path


def get_run_workspace_path(run_id: str) -> Path:
    return get_settings().workspace_root_path / f"run-{run_id}"


def cleanup_run_workspace(run_id: str) -> dict[str, object]:
    workspace_path = get_run_workspace_path(run_id)
    existed = workspace_path.exists()
    if existed:
        shutil.rmtree(workspace_path)
    return {"run_id": run_id, "workspace_path": str(workspace_path), "removed": existed}


def get_run_workspace_diff(run_id: str) -> dict[str, object]:
    workspace_path = get_run_workspace_path(run_id)
    if not workspace_path.exists():
        return {
            "workspace_path": str(workspace_path),
            "branch": "",
            "has_changes": False,
            "changed_files": [],
            "diff_text": "",
        }
    try:
        return get_workspace_diff(workspace_path)
    except ConfigurationError:
        return {
            "workspace_path": str(workspace_path),
            "branch": "",
            "has_changes": False,
            "changed_files": [],
            "diff_text": "",
        }


def list_run_workspace_files(run_id: str) -> dict[str, object]:
    workspace_path = get_run_workspace_path(run_id)
    if not workspace_path.exists():
        return {"run_id": run_id, "workspace_path": str(workspace_path), "files": []}

    try:
        files = list_workspace_files(workspace_path)
    except ConfigurationError:
        files = list_text_files(workspace_path)
    return {"run_id": run_id, "workspace_path": str(workspace_path), "files": files}


def read_run_workspace_file(run_id: str, relative_path: str) -> dict[str, object]:
    _ensure_safe_workspace_path(relative_path)
    workspace_path = get_run_workspace_path(run_id)
    content = read_text_file(workspace_path, relative_path)
    return {
        "run_id": run_id,
        "workspace_path": str(workspace_path),
        "path": relative_path,
        "content": content,
    }


def write_run_workspace_file(run_id: str, relative_path: str, content: str) -> dict[str, object]:
    _ensure_safe_workspace_path(relative_path)
    workspace_path = get_run_workspace_path(run_id)
    write_text_file(workspace_path, relative_path, content)
    return {
        "run_id": run_id,
        "workspace_path": str(workspace_path),
        "path": relative_path,
        "content": content,
    }


def delete_run_workspace_file(run_id: str, relative_path: str) -> dict[str, object]:
    _ensure_safe_workspace_path(relative_path)
    workspace_path = get_run_workspace_path(run_id)
    path = ensure_within_root(workspace_path / relative_path, workspace_path)
    if path.exists() and path.is_file():
        path.unlink()
        deleted = True
    else:
        deleted = False
    return {
        "run_id": run_id,
        "workspace_path": str(workspace_path),
        "path": relative_path,
        "deleted": deleted,
    }


def _ensure_safe_workspace_path(relative_path: str) -> None:
    path = Path(relative_path)
    if path.is_absolute() or not relative_path.strip() or ".git" in path.parts:
        raise ConfigurationError(f"Workspace path is not editable: {relative_path}")


def commit_run_workspace(run_id: str, message: str) -> dict[str, object]:
    settings = get_settings()
    workspace_path = get_run_workspace_path(run_id)
    commit_sha = commit_all_changes(
        workspace_path,
        message,
        settings.git_author_name,
        settings.git_author_email,
    )
    return {
        "run_id": run_id,
        "workspace_path": str(workspace_path),
        "branch": current_branch(workspace_path),
        "commit_sha": commit_sha,
    }


def _origin_fetch_url(remotes: list[str]) -> Optional[str]:
    """Return the fetch URL for the `origin` remote, if present."""
    for line in remotes:
        parts = line.split()
        if len(parts) >= 3 and parts[0] == "origin" and parts[-1] == "(fetch)":
            return parts[1]
    return None


def get_repository_config_snapshot() -> dict[str, object]:
    settings = get_settings()
    repo_summary = get_repository_summary()
    remotes = cast(list[str], repo_summary["remotes"])
    return {
        "source_repo_path": repo_summary["path"],
        "default_branch": repo_summary["branch"],
        "workspace_root": str(settings.workspace_root_path),
        "head_sha": repo_summary["head_sha"],
        "remotes": remotes,
        "origin_fetch_url": _origin_fetch_url(remotes),
        "dirty": repo_summary["dirty"],
    }
