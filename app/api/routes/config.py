
from typing import Optional

from fastapi import APIRouter, Depends, Header, HTTPException, status

from app.core.settings import get_settings

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
        "workspace_root": str(settings.workspace_root_path),
        "backup_root": str(settings.backup_root_path),
        "source_repo_path": (
            str(settings.source_repo_path_resolved) if settings.source_repo_path_resolved else None
        ),
        "worker_count": settings.worker_count,
        "provider_snapshot_policy": "future_runs_only",
        "git_transport": "host-managed",
        "github_api_auth": "app-managed-token",
    }
