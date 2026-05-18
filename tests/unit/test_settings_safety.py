"""Phase 2 tests: production-safety guard and SAFE_MODE editability."""

from __future__ import annotations

from pathlib import Path

import pytest

from app.core.exceptions import ConfigurationError
from app.core.settings import (
    INSECURE_API_TOKEN_DEFAULT,
    INSECURE_ENCRYPTION_KEY_DEFAULT,
    Settings,
    clear_settings_cache,
)
from app.services.settings_service import EDITABLE_ENV_KEYS, save_local_settings


def test_validate_production_safety_passes_in_development(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("APP_ENV", "development")
    monkeypatch.setenv("APP_API_TOKEN", INSECURE_API_TOKEN_DEFAULT)
    monkeypatch.setenv("APP_ENCRYPTION_KEY", INSECURE_ENCRYPTION_KEY_DEFAULT)
    clear_settings_cache()
    # In development mode the insecure defaults are allowed (no exception).
    Settings().validate_production_safety()


def test_validate_production_safety_fails_with_default_api_token(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("APP_API_TOKEN", INSECURE_API_TOKEN_DEFAULT)
    monkeypatch.setenv("APP_ENCRYPTION_KEY", "rotated-strong-key")
    clear_settings_cache()
    with pytest.raises(ConfigurationError) as excinfo:
        Settings().validate_production_safety()
    assert "APP_API_TOKEN" in str(excinfo.value)


def test_validate_production_safety_fails_with_default_encryption_key(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("APP_API_TOKEN", "rotated-strong-token")
    monkeypatch.setenv("APP_ENCRYPTION_KEY", INSECURE_ENCRYPTION_KEY_DEFAULT)
    clear_settings_cache()
    with pytest.raises(ConfigurationError) as excinfo:
        Settings().validate_production_safety()
    assert "APP_ENCRYPTION_KEY" in str(excinfo.value)


def test_validate_production_safety_lists_all_offenders(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("APP_API_TOKEN", INSECURE_API_TOKEN_DEFAULT)
    monkeypatch.setenv("APP_ENCRYPTION_KEY", INSECURE_ENCRYPTION_KEY_DEFAULT)
    clear_settings_cache()
    with pytest.raises(ConfigurationError) as excinfo:
        Settings().validate_production_safety()
    message = str(excinfo.value)
    assert "APP_API_TOKEN" in message
    assert "APP_ENCRYPTION_KEY" in message


def test_validate_production_safety_passes_with_rotated_secrets(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("APP_API_TOKEN", "rotated-strong-token")
    monkeypatch.setenv("APP_ENCRYPTION_KEY", "rotated-strong-key")
    clear_settings_cache()
    Settings().validate_production_safety()


def test_safe_mode_is_editable_via_settings_service(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """SAFE_MODE must be in EDITABLE_ENV_KEYS so operators can toggle it."""
    assert "SAFE_MODE" in EDITABLE_ENV_KEYS

    env_path = tmp_path / ".env"
    monkeypatch.setenv("APP_SETTINGS_FILE", str(env_path))
    monkeypatch.setenv("APP_API_TOKEN", "test-token")
    clear_settings_cache()

    save_local_settings({"SAFE_MODE": "false"})
    contents = env_path.read_text(encoding="utf-8")
    assert "SAFE_MODE=false" in contents

    save_local_settings({"SAFE_MODE": "true"})
    contents = env_path.read_text(encoding="utf-8")
    assert "SAFE_MODE=true" in contents
