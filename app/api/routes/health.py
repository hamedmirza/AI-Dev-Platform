
from fastapi import APIRouter

from app.db.session import get_engine
from app.providers.health import get_provider_health
from app.services.github_service import get_github_status
from app.services.repository_service import get_repository_summary

router = APIRouter(tags=["health"])


@router.get("/health")
def health() -> dict[str, str]:
    get_engine().connect().close()
    return {"status": "ok"}


@router.get("/health/provider")
def provider_health():
    return get_provider_health()


@router.get("/health/repository")
def repository_health():
    return get_repository_summary()


@router.get("/health/github")
def github_health():
    return get_github_status()
