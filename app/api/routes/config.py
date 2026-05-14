
from secrets import compare_digest
from typing import Optional

from fastapi import APIRouter, Depends, Header, HTTPException, Request, status

from app.core.settings import get_settings
from app.services.github_service import get_github_status, github_repo_metadata
from app.services.lmstudio_models_service import fetch_lmstudio_models
from app.services.repository_service import get_repository_config_snapshot

router = APIRouter(tags=["config"])


def require_api_token(
    request: Request,
    x_api_token: Optional[str] = Header(default=None),
) -> None:
    settings = get_settings()
    cookie_token = request.cookies.get("operator_token")
    header_ok = x_api_token is not None and compare_digest(x_api_token, settings.app_api_token)
    cookie_ok = cookie_token is not None and compare_digest(cookie_token, settings.app_api_token)
    if not header_ok and not cookie_ok:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing or invalid API token.",
        )


@router.get("/config", dependencies=[Depends(require_api_token)])
def config_summary() -> dict[str, object]:
    settings = get_settings()
    gh_repo = github_repo_metadata(settings)
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
            "lmstudio_model_planner": settings.lmstudio_model_planner or "",
            "lmstudio_model_architect": settings.lmstudio_model_architect or "",
            "lmstudio_model_ui_designer": settings.lmstudio_model_ui_designer or "",
            "lmstudio_model_coder": settings.lmstudio_model_coder or "",
            "lmstudio_model_reviewer": settings.lmstudio_model_reviewer or "",
            "lmstudio_model_tester": settings.lmstudio_model_tester or "",
            "lmstudio_model_supervisor": settings.lmstudio_model_supervisor or "",
            "lmstudio_api_key_configured": bool(settings.lmstudio_api_key.strip()),
            "provider_timeout_seconds": settings.provider_timeout_seconds,
            "planner_stage_timeout_seconds": settings.planner_stage_timeout_seconds,
            "planner_stage_max_retries": settings.planner_stage_max_retries,
            "allowed_git_hosts": settings.allowed_git_hosts,
            "allowed_source_repo_roots": settings.allowed_source_repo_roots,
            "git_clone_timeout_seconds": settings.git_clone_timeout_seconds,
            "source_repo_path": str(settings.source_repo_path_resolved or ""),
            "workspace_root": str(settings.workspace_root_path),
            "backup_root": str(settings.backup_root_path),
            "git_author_name": settings.git_author_name,
            "git_author_email": settings.git_author_email,
            "log_level": settings.log_level,
            "use_scout_stage": settings.use_scout_stage,
            "playbook_supervisor_enabled": settings.playbook_supervisor_enabled,
            "playbook_require_human_confirm": settings.playbook_require_human_confirm,
            "playbook_supervisor_system_prompt_path": (
                settings.playbook_supervisor_system_prompt_path
            ),
            "github_repo_full_name": gh_repo["repo_full_name"],
            "github_repo_default_branch": gh_repo["repo_default_branch"],
            "github_repo_html_url": gh_repo["repo_html_url"],
            "github_repo_clone_url": gh_repo["repo_clone_url"],
        },
        "repository": get_repository_config_snapshot(),
        "github": get_github_status(),
    }


@router.get("/config/lmstudio/models", dependencies=[Depends(require_api_token)])
def lmstudio_models_list() -> dict[str, object]:
    settings = get_settings()
    models, err = fetch_lmstudio_models(settings)
    return {"models": models, "error": err}
