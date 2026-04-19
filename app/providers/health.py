
from app.providers.registry import get_provider
from app.schemas.provider import ProviderHealthResponse


def get_provider_health() -> ProviderHealthResponse:
    return get_provider().healthcheck()
