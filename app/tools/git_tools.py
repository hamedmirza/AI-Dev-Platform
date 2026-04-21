
import subprocess
from pathlib import Path

from app.core.exceptions import ConfigurationError


def _run_git(args: list[str], cwd: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", *args],
        cwd=str(cwd),
        text=True,
        capture_output=True,
        check=False,
    )


def validate_git_repository(repo_path: Path) -> dict[str, object]:
    if not (repo_path / ".git").exists():
        raise ConfigurationError(f"Not a git repository: {repo_path}")

    branch = _run_git(["branch", "--show-current"], repo_path)
    remote = _run_git(["remote", "-v"], repo_path)
    status = _run_git(["status", "--short"], repo_path)

    if branch.returncode != 0:
        raise ConfigurationError(branch.stderr.strip() or "Unable to read git branch.")

    remotes = [line for line in remote.stdout.splitlines() if line.strip()]
    dirty = bool(status.stdout.strip())
    return {
        "path": str(repo_path),
        "branch": branch.stdout.strip() or "detached",
        "remotes": remotes,
        "dirty": dirty,
    }


def clone_local_repository(source_repo: Path, workspace_path: Path) -> None:
    result = _run_git(
        ["clone", "--quiet", "--no-hardlinks", str(source_repo), str(workspace_path)],
        source_repo,
    )
    if result.returncode != 0:
        raise ConfigurationError(result.stderr.strip() or "Failed to clone local repository.")


def checkout_new_branch(repo_path: Path, branch_name: str) -> None:
    result = _run_git(["checkout", "-b", branch_name], repo_path)
    if result.returncode != 0:
        raise ConfigurationError(result.stderr.strip() or "Failed to create workspace branch.")


def current_head_sha(repo_path: Path) -> str:
    result = _run_git(["rev-parse", "HEAD"], repo_path)
    if result.returncode != 0:
        raise ConfigurationError(result.stderr.strip() or "Failed to read current HEAD.")
    return result.stdout.strip()


def current_branch(repo_path: Path) -> str:
    result = _run_git(["branch", "--show-current"], repo_path)
    if result.returncode != 0:
        raise ConfigurationError(result.stderr.strip() or "Failed to read current branch.")
    return result.stdout.strip() or "detached"


def list_workspace_files(repo_path: Path) -> list[str]:
    result = _run_git(["ls-files"], repo_path)
    if result.returncode != 0:
        raise ConfigurationError(result.stderr.strip() or "Failed to list tracked files.")
    files = [line.strip() for line in result.stdout.splitlines() if line.strip()]

    untracked = _run_git(["ls-files", "--others", "--exclude-standard"], repo_path)
    if untracked.returncode != 0:
        raise ConfigurationError(untracked.stderr.strip() or "Failed to list untracked files.")
    files.extend(line.strip() for line in untracked.stdout.splitlines() if line.strip())
    return sorted(set(files))


def commit_all_changes(
    repo_path: Path,
    message: str,
    author_name: str,
    author_email: str,
) -> str:
    add_result = _run_git(["add", "-A"], repo_path)
    if add_result.returncode != 0:
        raise ConfigurationError(add_result.stderr.strip() or "Failed to stage workspace changes.")

    status = _run_git(["status", "--short"], repo_path)
    if status.returncode != 0:
        raise ConfigurationError(status.stderr.strip() or "Failed to inspect workspace status.")
    if not status.stdout.strip():
        return current_head_sha(repo_path)

    result = _run_git(
        [
            "-c",
            f"user.name={author_name}",
            "-c",
            f"user.email={author_email}",
            "commit",
            "-m",
            message,
        ],
        repo_path,
    )
    if result.returncode != 0:
        raise ConfigurationError(result.stderr.strip() or "Failed to commit workspace changes.")
    return current_head_sha(repo_path)


def get_workspace_diff(repo_path: Path) -> dict[str, object]:
    if not (repo_path / ".git").exists():
        raise ConfigurationError(f"Not a git repository: {repo_path}")

    status = _run_git(["status", "--short"], repo_path)
    diff = _run_git(["diff", "--no-ext-diff"], repo_path)
    untracked = _run_git(["ls-files", "--others", "--exclude-standard"], repo_path)

    if status.returncode != 0 or diff.returncode != 0 or untracked.returncode != 0:
        raise ConfigurationError("Failed to compute repository diff.")

    status_lines = [line for line in status.stdout.splitlines() if line.strip()]
    changed_files = [line[3:] if len(line) > 3 else line for line in status_lines]
    diff_text = diff.stdout.strip()
    untracked_files = [line for line in untracked.stdout.splitlines() if line.strip()]

    if not diff_text and untracked_files:
        diff_text = "Untracked files:\n" + "\n".join(untracked_files)

    return {
        "workspace_path": str(repo_path),
        "branch": current_branch(repo_path),
        "has_changes": bool(status_lines),
        "changed_files": changed_files,
        "diff_text": diff_text,
    }
