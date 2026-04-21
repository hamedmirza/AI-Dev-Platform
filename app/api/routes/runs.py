
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.api.routes.config import require_api_token
from app.core.exceptions import WorkflowError
from app.db.session import get_db
from app.schemas.diff import DiffResponse
from app.schemas.run import RunActionRequest, RunActionResponse
from app.schemas.workspace import (
    WorkspaceFileResponse,
    WorkspaceFilesResponse,
    WorkspaceFileUpdateRequest,
    WorkspaceFileUpdateResponse,
)
from app.services.artifact_service import list_artifacts
from app.services.orchestration_service import get_orchestration_service
from app.services.repository_service import (
    get_run_workspace_diff,
    list_run_workspace_files,
    read_run_workspace_file,
    write_run_workspace_file,
)
from app.services.run_service import (
    abort_run,
    approve_run,
    cleanup_workspace,
    get_run,
    get_run_history,
    reject_run,
    retry_run,
)

router = APIRouter(tags=["runs"])


@router.get("/runs/{run_id}", dependencies=[Depends(require_api_token)])
def fetch_run(run_id: str, session: Session = Depends(get_db)):
    run = get_run(session, run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="Run not found.")
    return run


@router.get("/runs/{run_id}/history", dependencies=[Depends(require_api_token)])
def fetch_run_history(run_id: str, session: Session = Depends(get_db)):
    return get_run_history(session, run_id)


@router.get("/runs/{run_id}/artifacts", dependencies=[Depends(require_api_token)])
def fetch_run_artifacts(run_id: str, session: Session = Depends(get_db)):
    return list_artifacts(session, run_id)


@router.get(
    "/runs/{run_id}/diff",
    dependencies=[Depends(require_api_token)],
    response_model=DiffResponse,
)
def fetch_run_diff(run_id: str):
    return get_run_workspace_diff(run_id)


@router.get(
    "/runs/{run_id}/workspace/files",
    dependencies=[Depends(require_api_token)],
    response_model=WorkspaceFilesResponse,
)
def fetch_workspace_files(run_id: str):
    return list_run_workspace_files(run_id)


@router.get(
    "/runs/{run_id}/workspace/file",
    dependencies=[Depends(require_api_token)],
    response_model=WorkspaceFileResponse,
)
def fetch_workspace_file(run_id: str, path: str):
    try:
        return read_run_workspace_file(run_id, path)
    except WorkflowError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post(
    "/runs/{run_id}/workspace/file",
    dependencies=[Depends(require_api_token)],
    response_model=WorkspaceFileUpdateResponse,
)
def update_workspace_file(run_id: str, payload: WorkspaceFileUpdateRequest):
    try:
        return write_run_workspace_file(run_id, payload.path, payload.content)
    except Exception as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.post(
    "/runs/{run_id}/approve",
    dependencies=[Depends(require_api_token)],
    response_model=RunActionResponse,
)
def approve(run_id: str, payload: RunActionRequest, session: Session = Depends(get_db)):
    try:
        run = approve_run(session, run_id, payload.note)
    except WorkflowError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return RunActionResponse(run_id=run.id, status=run.status, message="Run approved.")


@router.post(
    "/runs/{run_id}/reject",
    dependencies=[Depends(require_api_token)],
    response_model=RunActionResponse,
)
def reject(run_id: str, payload: RunActionRequest, session: Session = Depends(get_db)):
    try:
        run = reject_run(session, run_id, payload.note)
    except WorkflowError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return RunActionResponse(run_id=run.id, status=run.status, message="Run rejected.")


@router.post(
    "/runs/{run_id}/retry",
    dependencies=[Depends(require_api_token)],
    response_model=RunActionResponse,
)
def retry(run_id: str, payload: RunActionRequest, session: Session = Depends(get_db)):
    try:
        run = retry_run(session, run_id, payload.note)
    except WorkflowError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    get_orchestration_service().enqueue_run(run_id)
    return RunActionResponse(run_id=run.id, status=run.status, message="Run marked pending.")


@router.post(
    "/runs/{run_id}/abort",
    dependencies=[Depends(require_api_token)],
    response_model=RunActionResponse,
)
def abort(run_id: str, payload: RunActionRequest, session: Session = Depends(get_db)):
    try:
        run = abort_run(session, run_id, payload.note)
    except WorkflowError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return RunActionResponse(run_id=run.id, status=run.status, message="Run cancelled.")


@router.post("/runs/{run_id}/cleanup-workspace", dependencies=[Depends(require_api_token)])
def cleanup(run_id: str):
    return cleanup_workspace(run_id)
