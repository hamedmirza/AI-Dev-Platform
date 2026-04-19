
from fastapi import APIRouter

from app.db.session import get_engine
from app.providers.health import get_provider_health

router = APIRouter(tags=["health"])


@router.get("/health")
def health() -> dict[str, str]:
    get_engine().connect().close()
    return {"status": "ok"}


@router.get("/health/provider")
def provider_health():
    return get_provider_health()
