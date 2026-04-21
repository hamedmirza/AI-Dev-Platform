
from typing import Optional

from fastapi import APIRouter, Depends, Header, HTTPException, status

from app.core.settings import get_settings
from app.services.github_service import get_github_status
from app.services.repository_service import get_repository_config_snapshot

router = APIRouter(tags=["config"])


def require_api_token(x_api_token: Optional[str] = Header(default=None)) -> None:
    settings = get_settings()
    if x_api_token != settings.app_api_token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing or invalid API token.",
        )


@router.get("/config", dependencies=[Depends(require_api_token)])
def config_summary() -> dict[str, object]:
    settings = get_settings()
    return {
        "app_env": settings.app_env,
        "model_provider": settings.model_provider,
        "backup_root": str(settings.backup_root_path),
        "worker_count": settings.worker_count,
        "provider_snapshot_policy": "future_runs_only",
        "git_transport": "host-managed",
        "github_api_auth": "app-managed-token",
        "repository": get_repository_config_snapshot(),
        "github": get_github_status(),
    }
