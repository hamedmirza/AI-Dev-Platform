
from functools import lru_cache
from pathlib import Path
from typing import Optional

from pydantic import Field
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
    lmstudio_api_key: str = Field(default="lm-studio", alias="LMSTUDIO_API_KEY")
    provider_timeout_seconds: float = Field(default=60.0, alias="PROVIDER_TIMEOUT_SECONDS")

    workspace_root: str = Field(default="./workspace", alias="WORKSPACE_ROOT")
    source_repo_path: Optional[str] = Field(default=None, alias="SOURCE_REPO_PATH")
    backup_root: str = Field(default="./backups", alias="BACKUP_ROOT")
    encryption_key: str = Field(default="change-me", alias="APP_ENCRYPTION_KEY")
    git_author_name: str = Field(default="AI Dev Platform", alias="GIT_AUTHOR_NAME")
    git_author_email: str = Field(
        default="ai-dev-platform@example.com",
        alias="GIT_AUTHOR_EMAIL",
    )

    worker_count: int = Field(default=1, alias="WORKER_COUNT")
    artifact_char_limit: int = Field(default=12000, alias="ARTIFACT_CHAR_LIMIT")
    log_level: str = Field(default="INFO", alias="LOG_LEVEL")

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
