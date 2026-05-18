
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.api.routes.config import require_api_token
from app.core.enums import RunStatus
from app.core.exceptions import WorkflowError
from app.db.models import RunModel
from app.db.session import get_db
from app.schemas.diff import DiffResponse
from app.schemas.run import (
    RunActionRequest,
    RunActionResponse,
    RunHistoryCleanupResponse,
)
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
    clear_terminal_run_history,
    get_run,
    get_run_history,
    get_run_state_snapshots,
    list_runs,
    reject_run,
    retry_run,
)

router = APIRouter(tags=["runs"])


@router.get("/runs", dependencies=[Depends(require_api_token)])
def fetch_runs(
    limit: int = Query(default=12, ge=1, le=100),
    session: Session = Depends(get_db),
):
    return list_runs(session, limit=limit)


@router.post(
    "/runs/clear-terminal-history",
    dependencies=[Depends(require_api_token)],
    response_model=RunHistoryCleanupResponse,
)
def clear_terminal_history(
    keep_latest: int = Query(default=4, ge=0, le=50),
    cleanup_workspaces: bool = Query(default=True),
    session: Session = Depends(get_db),
):
    return clear_terminal_run_history(
        session,
        keep_latest=keep_latest,
        cleanup_workspaces=cleanup_workspaces,
    )


@router.get("/runs/{run_id}", dependencies=[Depends(require_api_token)])
def fetch_run(run_id: str, session: Session = Depends(get_db)):
    run = get_run(session, run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="Run not found.")
    return run


@router.get("/runs/{run_id}/history", dependencies=[Depends(require_api_token)])
def fetch_run_history(run_id: str, session: Session = Depends(get_db)):
    return get_run_history(session, run_id)


@router.get("/runs/{run_id}/state-snapshots", dependencies=[Depends(require_api_token)])
def fetch_run_state_snapshots(run_id: str, session: Session = Depends(get_db)):
    return get_run_state_snapshots(session, run_id)


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
    "/runs/{run_id}/retry-from-blocker",
    dependencies=[Depends(require_api_token)],
    response_model=RunActionResponse,
)
def retry_from_blocker(
    run_id: str,
    payload: RunActionRequest,
    session: Session = Depends(get_db),
):
    run_response = get_run(session, run_id)
    if run_response is None:
        raise HTTPException(status_code=404, detail="Run not found.")
    if run_response.active_blocker is None:
        raise HTTPException(status_code=409, detail="Run does not have an active blocker.")
    note = payload.note or run_response.active_blocker.suggested_retry_instruction
    try:
        run = retry_run(session, run_id, note)
    except WorkflowError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    get_orchestration_service().enqueue_run(run_id)
    return RunActionResponse(
        run_id=run.id,
        status=run.status,
        message="Run marked pending from active blocker.",
    )


@router.post("/runs/{run_id}/validate", dependencies=[Depends(require_api_token)])
def validate_run(run_id: str):
    try:
        return get_orchestration_service().validate_run_workspace(run_id)
    except WorkflowError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.post(
    "/runs/{run_id}/mark-manual-repair-validated",
    dependencies=[Depends(require_api_token)],
)
def mark_manual_repair_validated(run_id: str):
    try:
        return get_orchestration_service().validate_run_workspace(run_id, mark_repaired=True)
    except WorkflowError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.post(
    "/runs/{run_id}/abort",
    dependencies=[Depends(require_api_token)],
    response_model=RunActionResponse,
)
def abort(run_id: str, payload: RunActionRequest, session: Session = Depends(get_db)):
    pre = session.get(RunModel, run_id)
    was_running = pre is not None and pre.status == RunStatus.RUNNING
    try:
        run = abort_run(session, run_id, payload.note)
    except WorkflowError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    if was_running:
        message = (
            "Cancellation requested. The worker will stop at the next checkpoint "
            "(the current step may complete first)."
        )
    else:
        message = "Run cancelled."
    return RunActionResponse(run_id=run.id, status=run.status, message=message)


@router.post("/runs/{run_id}/cleanup-workspace", dependencies=[Depends(require_api_token)])
def cleanup(run_id: str, session: Session = Depends(get_db)):
    try:
        return cleanup_workspace(session, run_id)
    except WorkflowError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
