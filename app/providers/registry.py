
from typing import Optional

from app.core.exceptions import ConfigurationError
from app.core.settings import get_settings
from app.providers.base import BaseProvider
from app.providers.lmstudio import LMStudioProvider

_provider_override: Optional[BaseProvider] = None


def set_provider_override(provider: Optional[BaseProvider]) -> None:
    global _provider_override
    _provider_override = provider


def get_provider() -> BaseProvider:
    if _provider_override is not None:
        return _provider_override

    settings = get_settings()
    if settings.model_provider == "lmstudio":
        return LMStudioProvider(settings)
    raise ConfigurationError(f"Unsupported model provider: {settings.model_provider}")
