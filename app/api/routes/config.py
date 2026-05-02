
from typing import Optional

from fastapi import APIRouter, Depends, Header, HTTPException, Request, status

from app.core.settings import get_settings
from app.services.github_service import get_github_status
from app.services.repository_service import get_repository_config_snapshot

router = APIRouter(tags=["config"])


def require_api_token(
    request: Request,
    x_api_token: Optional[str] = Header(default=None),
) -> None:
    settings = get_settings()
    cookie_token = request.cookies.get("operator_token")
    if x_api_token != settings.app_api_token and cookie_token != settings.app_api_token:
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
        "runtime": {
            "app_host": settings.app_host,
            "app_port": settings.app_port,
            "lmstudio_base_url": settings.lmstudio_base_url,
            "lmstudio_model": settings.lmstudio_model,
            "lmstudio_api_key": settings.lmstudio_api_key,
            "provider_timeout_seconds": settings.provider_timeout_seconds,
            "source_repo_path": str(settings.source_repo_path_resolved or ""),
            "workspace_root": str(settings.workspace_root_path),
            "backup_root": str(settings.backup_root_path),
            "git_author_name": settings.git_author_name,
            "git_author_email": settings.git_author_email,
            "log_level": settings.log_level,
        },
        "repository": get_repository_config_snapshot(),
        "github": get_github_status(),
    }
