
from functools import lru_cache
from pathlib import Path
from typing import Optional

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_env: str = Field(default="development", alias="APP_ENV")
    app_host: str = Field(default="0.0.0.0", alias="APP_HOST")
    app_port: int = Field(default=8400, alias="APP_PORT")
    app_api_token: str = Field(default="dev-token", alias="APP_API_TOKEN")

    db_url: str = Field(default="sqlite:///./app.db", alias="DB_URL")

    model_provider: str = Field(default="lmstudio", alias="MODEL_PROVIDER")
    lmstudio_base_url: str = Field(default="http://localhost:1234/v1", alias="LMSTUDIO_BASE_URL")
    lmstudio_model: str = Field(
        default="qwen2.5-coder-14b-instruct",
        alias="LMSTUDIO_MODEL",
    )
    lmstudio_model_planner: Optional[str] = Field(default=None, alias="LMSTUDIO_MODEL_PLANNER")
    lmstudio_model_architect: Optional[str] = Field(default=None, alias="LMSTUDIO_MODEL_ARCHITECT")
    lmstudio_model_ui_designer: Optional[str] = Field(
        default=None,
        alias="LMSTUDIO_MODEL_UI_DESIGNER",
    )
    lmstudio_model_coder: Optional[str] = Field(default=None, alias="LMSTUDIO_MODEL_CODER")
    lmstudio_model_reviewer: Optional[str] = Field(default=None, alias="LMSTUDIO_MODEL_REVIEWER")
    lmstudio_model_tester: Optional[str] = Field(default=None, alias="LMSTUDIO_MODEL_TESTER")
    lmstudio_model_supervisor: Optional[str] = Field(
        default=None,
        alias="LMSTUDIO_MODEL_SUPERVISOR",
    )
    lmstudio_api_key: str = Field(default="lm-studio", alias="LMSTUDIO_API_KEY")
    provider_timeout_seconds: float = Field(default=60.0, alias="PROVIDER_TIMEOUT_SECONDS")
    planner_stage_timeout_seconds: float = Field(
        default=45.0,
        alias="PLANNER_STAGE_TIMEOUT_SECONDS",
    )
    planner_stage_max_retries: int = Field(default=2, alias="PLANNER_STAGE_MAX_RETRIES")

    workspace_root: str = Field(default="./workspace", alias="WORKSPACE_ROOT")
    source_repo_path: Optional[str] = Field(default=None, alias="SOURCE_REPO_PATH")
    allowed_git_hosts: str = Field(default="", alias="ALLOWED_GIT_HOSTS")
    # Canonical GitHub repo for this platform (owner/repo, shown in settings / health).
    github_repo_full_name: str = Field(
        default="hamedmirza/AI-Dev-Platform",
        alias="GITHUB_REPO_FULL_NAME",
    )
    github_repo_default_branch: str = Field(default="main", alias="GITHUB_REPO_DEFAULT_BRANCH")
    allowed_source_repo_roots: str = Field(default="", alias="ALLOWED_SOURCE_REPO_ROOTS")
    git_clone_timeout_seconds: float = Field(default=300.0, alias="GIT_CLONE_TIMEOUT_SECONDS")
    backup_root: str = Field(default="./backups", alias="BACKUP_ROOT")
    encryption_key: str = Field(default="change-me", alias="APP_ENCRYPTION_KEY")
    git_author_name: str = Field(default="AI Dev Platform", alias="GIT_AUTHOR_NAME")
    git_author_email: str = Field(
        default="ai-dev-platform@example.com",
        alias="GIT_AUTHOR_EMAIL",
    )

    worker_count: int = Field(default=3, alias="WORKER_COUNT")
    artifact_char_limit: int = Field(default=12000, alias="ARTIFACT_CHAR_LIMIT")
    log_level: str = Field(default="INFO", alias="LOG_LEVEL")

    use_scout_stage: bool = Field(default=False, alias="USE_SCOUT_STAGE")
    playbook_supervisor_enabled: bool = Field(default=False, alias="PLAYBOOK_SUPERVISOR_ENABLED")
    playbook_require_human_confirm: bool = Field(
        default=True,
        alias="PLAYBOOK_REQUIRE_HUMAN_CONFIRM",
    )
    playbook_supervisor_system_prompt_path: str = Field(
        default="app/agents/prompts/playbook_supervisor.md",
        alias="PLAYBOOK_SUPERVISOR_SYSTEM_PROMPT_PATH",
    )
    playbook_char_limit: int = Field(default=8000, alias="PLAYBOOK_CHAR_LIMIT")
    repo_lesson_max_lines: int = Field(default=40, alias="REPO_LESSON_MAX_LINES")

    @field_validator("github_repo_full_name", mode="before")
    @classmethod
    def normalize_github_repo_full_name(cls, value: object) -> str:
        if value is None:
            return ""
        s = str(value).strip()
        for prefix in ("https://github.com/", "http://github.com/"):
            if s.lower().startswith(prefix):
                s = s[len(prefix) :]
        if s.lower().startswith("github.com/"):
            s = s.split("/", 1)[1] if "/" in s else ""
        if s.endswith(".git"):
            s = s[:-4]
        return s.strip().strip("/")

    @field_validator("github_repo_default_branch", mode="before")
    @classmethod
    def normalize_default_branch(cls, value: object) -> str:
        if value is None:
            return "main"
        b = str(value).strip()
        return b if b else "main"

    @property
    def workspace_root_path(self) -> Path:
        return Path(self.workspace_root).resolve()

    @property
    def backup_root_path(self) -> Path:
        return Path(self.backup_root).resolve()

    @property
    def source_repo_path_resolved(self) -> Optional[Path]:
        if self.source_repo_path:
            return Path(self.source_repo_path).resolve()

        cwd = Path.cwd().resolve()
        if (cwd / ".git").exists():
            return cwd
        return None


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()


def clear_settings_cache() -> None:
    get_settings.cache_clear()
