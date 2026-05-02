import pytest

from app.core.exceptions import ConfigurationError
from app.core.settings import Settings
from app.services.source_repo_policy import validate_source_repo_spec


def test_remote_requires_allowlist() -> None:
    settings = Settings().model_copy(
        update={"allowed_git_hosts": "", "allowed_source_repo_roots": ""},
    )
    with pytest.raises(ConfigurationError, match="ALLOWED_GIT_HOSTS"):
        validate_source_repo_spec("https://github.com/foo/bar.git", settings)


def test_remote_host_must_match() -> None:
    settings = Settings().model_copy(
        update={"allowed_git_hosts": "gitlab.com", "allowed_source_repo_roots": ""},
    )
    with pytest.raises(ConfigurationError, match="ALLOWED_GIT_HOSTS"):
        validate_source_repo_spec("https://github.com/foo/bar.git", settings)


def test_remote_allowed() -> None:
    settings = Settings().model_copy(
        update={
            "allowed_git_hosts": "github.com",
            "allowed_source_repo_roots": "",
        }
    )
    resolved = validate_source_repo_spec("https://github.com/foo/bar.git", settings)
    assert resolved.kind == "remote"
    assert resolved.remote_url == "https://github.com/foo/bar.git"


def test_local_requires_git_dir(tmp_path) -> None:
    settings = Settings().model_copy(
        update={"allowed_git_hosts": "", "allowed_source_repo_roots": ""},
    )
    bare = tmp_path / "repo"
    bare.mkdir()
    (bare / ".git").mkdir()
    resolved = validate_source_repo_spec(str(bare), settings)
    assert resolved.kind == "local"
    assert resolved.local_path == bare.resolve()
