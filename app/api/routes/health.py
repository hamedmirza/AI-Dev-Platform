
from fastapi import APIRouter, HTTPException, status

from app.db.session import get_engine
from app.providers.health import get_provider_health
from app.services.github_service import get_github_status
from app.services.repository_service import get_repository_summary

router = APIRouter(tags=["health"])


@router.get("/health/live")
def health_live() -> dict[str, str]:
    """Liveness: process is up (no dependency checks)."""
    return {"status": "live"}


@router.get("/health/ready")
def health_ready() -> dict[str, object]:
    """Readiness: database reachable; provider status is informational (soft check)."""
    try:
        get_engine().connect().close()
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={"status": "not_ready", "database": "unreachable"},
        ) from exc
    provider = get_provider_health()
    return {
        "status": "ready",
        "database": "ok",
        "provider": provider.status.value,
        "provider_detail": provider.detail,
    }


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
