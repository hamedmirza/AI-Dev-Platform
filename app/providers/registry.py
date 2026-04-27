
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
    return resolve_provider()


def resolve_provider(
    provider_name: Optional[str] = None,
    model_name: Optional[str] = None,
) -> BaseProvider:
    if _provider_override is not None:
        return _provider_override.with_overrides(provider_name=provider_name, model_name=model_name)

    settings = get_settings()
    selected_provider = provider_name or settings.model_provider
    if selected_provider == "lmstudio":
        provider_settings = settings
        if model_name:
            provider_settings = settings.model_copy(update={"lmstudio_model": model_name})
        return LMStudioProvider(provider_settings)
    raise ConfigurationError(f"Unsupported model provider: {selected_provider}")
