import shutil
from pathlib import Path

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
    commit_all_changes,
    current_branch,
    current_head_sha,
    get_workspace_diff,
    list_workspace_files,
    validate_git_repository,
)


def get_repository_summary() -> dict[str, object]:
    repo_path = require_source_repo()
    summary = validate_git_repository(repo_path)
    summary["head_sha"] = current_head_sha(repo_path)
    return summary


def create_run_workspace(run_id: str) -> Path:
    repo_path = require_source_repo()
    workspace_path = prepare_workspace_directory(run_id)
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
    workspace_path = get_run_workspace_path(run_id)
    content = read_text_file(workspace_path, relative_path)
    return {
        "run_id": run_id,
        "workspace_path": str(workspace_path),
        "path": relative_path,
        "content": content,
    }


def write_run_workspace_file(run_id: str, relative_path: str, content: str) -> dict[str, object]:
    workspace_path = get_run_workspace_path(run_id)
    write_text_file(workspace_path, relative_path, content)
    return {
        "run_id": run_id,
        "workspace_path": str(workspace_path),
        "path": relative_path,
        "content": content,
    }


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


def get_repository_config_snapshot() -> dict[str, object]:
    settings = get_settings()
    repo_summary = get_repository_summary()
    return {
        "source_repo_path": repo_summary["path"],
        "default_branch": repo_summary["branch"],
        "workspace_root": str(settings.workspace_root_path),
        "head_sha": repo_summary["head_sha"],
        "remotes": repo_summary["remotes"],
        "dirty": repo_summary["dirty"],
    }
