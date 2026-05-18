import os
from pathlib import Path

from app.core.settings import clear_settings_cache, get_settings

EDITABLE_ENV_KEYS = {
    "APP_HOST",
    "APP_PORT",
    "APP_API_TOKEN",
    "LMSTUDIO_BASE_URL",
    "LMSTUDIO_MODEL",
    "LMSTUDIO_MODEL_PLANNER",
    "LMSTUDIO_MODEL_ARCHITECT",
    "LMSTUDIO_MODEL_UI_DESIGNER",
    "LMSTUDIO_MODEL_CODER",
    "LMSTUDIO_MODEL_REVIEWER",
    "LMSTUDIO_MODEL_TESTER",
    "LMSTUDIO_MODEL_SUPERVISOR",
    "LMSTUDIO_API_KEY",
    "PROVIDER_TIMEOUT_SECONDS",
    "SOURCE_REPO_PATH",
    "ALLOWED_GIT_HOSTS",
    "GITHUB_REPO_FULL_NAME",
    "GITHUB_REPO_DEFAULT_BRANCH",
    "ALLOWED_SOURCE_REPO_ROOTS",
    "GIT_CLONE_TIMEOUT_SECONDS",
    "WORKER_COUNT",
    "WORKSPACE_ROOT",
    "BACKUP_ROOT",
    "GIT_AUTHOR_NAME",
    "GIT_AUTHOR_EMAIL",
    "LOG_LEVEL",
    "USE_SCOUT_STAGE",
    "PLAYBOOK_SUPERVISOR_ENABLED",
    "PLAYBOOK_REQUIRE_HUMAN_CONFIRM",
    "PLAYBOOK_SUPERVISOR_SYSTEM_PROMPT_PATH",
    "PLAYBOOK_CHAR_LIMIT",
    "REPO_LESSON_MAX_LINES",
}

POSITIVE_INT_ENV_KEYS = {
    "APP_PORT",
    "WORKER_COUNT",
    "PLAYBOOK_CHAR_LIMIT",
    "REPO_LESSON_MAX_LINES",
}

POSITIVE_FLOAT_ENV_KEYS = {
    "PROVIDER_TIMEOUT_SECONDS",
    "GIT_CLONE_TIMEOUT_SECONDS",
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

    _validate_local_settings(current)
    lines = [f"{key}={current[key]}" for key in sorted(current)]
    _env_path().write_text("\n".join(lines) + "\n", encoding="utf-8")
    clear_settings_cache()
    get_settings()


def _validate_local_settings(values: dict[str, str]) -> None:
    for key in POSITIVE_INT_ENV_KEYS:
        raw_value = values.get(key)
        if raw_value is None or raw_value == "":
            continue
        try:
            parsed = int(raw_value)
        except ValueError as exc:
            raise ValueError(f"{key} must be an integer.") from exc
        if parsed <= 0:
            raise ValueError(f"{key} must be greater than zero.")

    for key in POSITIVE_FLOAT_ENV_KEYS:
        raw_value = values.get(key)
        if raw_value is None or raw_value == "":
            continue
        try:
            parsed = float(raw_value)
        except ValueError as exc:
            raise ValueError(f"{key} must be a number.") from exc
        if parsed <= 0:
            raise ValueError(f"{key} must be greater than zero.")
