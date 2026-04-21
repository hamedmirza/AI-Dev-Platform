import os
from pathlib import Path

from app.core.settings import clear_settings_cache, get_settings

EDITABLE_ENV_KEYS = {
    "APP_HOST",
    "APP_PORT",
    "APP_API_TOKEN",
    "LMSTUDIO_BASE_URL",
    "LMSTUDIO_MODEL",
    "LMSTUDIO_API_KEY",
    "PROVIDER_TIMEOUT_SECONDS",
    "SOURCE_REPO_PATH",
    "WORKSPACE_ROOT",
    "BACKUP_ROOT",
    "GIT_AUTHOR_NAME",
    "GIT_AUTHOR_EMAIL",
    "LOG_LEVEL",
}


def _env_path() -> Path:
    configured = os.environ.get("APP_SETTINGS_FILE")
    if configured:
        return Path(configured).resolve()
    return Path(".env").resolve()


def load_local_settings() -> dict[str, str]:
    env_path = _env_path()
    if not env_path.exists():
        return {}

    values: dict[str, str] = {}
    for line in env_path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, value = stripped.split("=", 1)
        values[key.strip()] = value.strip()
    return values


def save_local_settings(updates: dict[str, str]) -> None:
    current = load_local_settings()
    for key, value in updates.items():
        if key in EDITABLE_ENV_KEYS:
            current[key] = value

    lines = [f"{key}={current[key]}" for key in sorted(current)]
    _env_path().write_text("\n".join(lines) + "\n", encoding="utf-8")
    clear_settings_cache()
    get_settings()
