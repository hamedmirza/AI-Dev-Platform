from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.api.routes.config import require_api_token
from app.core.exceptions import ConfigurationError
from app.db.session import get_db
from app.schemas.source_repo import (
    SavedSourceRepoResponse,
    SourceRepoSaveRequest,
    SourceRepoValidateRequest,
    SourceRepoValidationResponse,
)
from app.services.source_repo_service import (
    delete_saved_source_repo,
    list_saved_source_repos,
    save_source_repo,
    validate_source_repo_for_operator,
)

router = APIRouter(tags=["source-repos"], dependencies=[Depends(require_api_token)])


@router.get("/source-repos", response_model=list[SavedSourceRepoResponse])
def source_repos_list(session: Session = Depends(get_db)) -> list[SavedSourceRepoResponse]:
    try:
        return list_saved_source_repos(session)
    except ConfigurationError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.post("/source-repos/validate", response_model=SourceRepoValidationResponse)
def source_repos_validate(payload: SourceRepoValidateRequest) -> SourceRepoValidationResponse:
    try:
        return validate_source_repo_for_operator(payload.source_repo)
    except ConfigurationError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.post("/source-repos", response_model=SavedSourceRepoResponse)
def source_repos_save(
    payload: SourceRepoSaveRequest,
    session: Session = Depends(get_db),
) -> SavedSourceRepoResponse:
    try:
        return save_source_repo(session, payload.source_repo, payload.label)
    except ConfigurationError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.delete("/source-repos/{repo_id}")
def source_repos_delete(repo_id: str, session: Session = Depends(get_db)) -> dict[str, object]:
    try:
        delete_saved_source_repo(session, repo_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return {"deleted": True, "id": repo_id}
