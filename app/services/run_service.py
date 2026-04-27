
from typing import Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.enums import RunStage, RunStatus
from app.core.exceptions import WorkflowError
from app.db.models import RunEventModel, RunModel, RunStateSnapshotModel
from app.schemas.run import (
    RunEventResponse,
    RunResponse,
    RunStateSnapshotResponse,
    TaskSummaryResponse,
)
from app.services.repository_service import (
    cleanup_run_workspace,
    commit_run_workspace,
    get_run_workspace_diff,
)


def get_run(session: Session, run_id: str) -> Optional[RunResponse]:
    model = session.get(RunModel, run_id)
    if model is None:
        return None
    latest_state_model = session.scalars(
        select(RunStateSnapshotModel)
        .where(RunStateSnapshotModel.run_id == run_id)
        .order_by(RunStateSnapshotModel.id.desc())
        .limit(1)
    ).first()
    return RunResponse(
        id=model.id,
        task_id=model.task_id,
        status=model.status,
        current_stage=model.current_stage,
        provider_name=model.provider_name,
        request_id=model.request_id,
        retry_count=model.retry_count,
        error_message=model.error_message,
        created_at=model.created_at,
        updated_at=model.updated_at,
        task=TaskSummaryResponse(
            id=model.task.id,
            title=model.task.title,
            description=model.task.description,
            workspace_path=model.task.workspace_path,
            task_type=model.task.task_type,
            constraints=model.task.constraints,
            target_files=model.task.target_files,
            provider_override=model.task.provider_override,
            model_override=model.task.model_override,
            request_text=model.task.request_text,
        ),
        latest_state=_to_snapshot_response(latest_state_model),
    )


def get_run_history(session: Session, run_id: str) -> list[RunEventResponse]:
    events = session.scalars(
        select(RunEventModel).where(RunEventModel.run_id == run_id).order_by(RunEventModel.id.asc())
    ).all()
    return [
        RunEventResponse(
            id=item.id,
            event_type=item.event_type,
            message=item.message,
            payload_json=item.payload_json,
            created_at=item.created_at,
        )
        for item in events
    ]


def get_run_state_snapshots(session: Session, run_id: str) -> list[RunStateSnapshotResponse]:
    snapshots = session.scalars(
        select(RunStateSnapshotModel)
        .where(RunStateSnapshotModel.run_id == run_id)
        .order_by(RunStateSnapshotModel.id.asc())
    ).all()
    responses: list[RunStateSnapshotResponse] = []
    for item in snapshots:
        response = _to_snapshot_response(item)
        if response is not None:
            responses.append(response)
    return responses


def _record_event(
    session: Session,
    run: RunModel,
    event_type: str,
    message: str,
    payload_json: Optional[str] = None,
) -> None:
    session.add(
        RunEventModel(
            run_id=run.id,
            event_type=event_type,
            message=message,
            payload_json=payload_json,
        )
    )


def approve_run(session: Session, run_id: str, note: Optional[str] = None) -> RunResponse:
    run = session.get(RunModel, run_id)
    if run is None:
        raise WorkflowError("Run not found.")
    if run.status != RunStatus.AWAITING_APPROVAL:
        raise WorkflowError("Run is not awaiting approval.")

    diff = get_run_workspace_diff(run_id)
    if bool(diff["has_changes"]):
        commit_result = commit_run_workspace(run_id, f"run {run_id}: operator approved")
        _record_event(
            session,
            run,
            "workspace_committed",
            "Workspace changes were committed during operator approval.",
            payload_json=str(commit_result["commit_sha"]),
        )

    run.status = RunStatus.COMPLETED
    run.current_stage = RunStage.DONE
    run.error_message = None
    _record_event(session, run, "operator_approved", note or "Operator approved the run.")
    session.commit()
    result = get_run(session, run_id)
    assert result is not None
    return result


def reject_run(session: Session, run_id: str, note: Optional[str] = None) -> RunResponse:
    run = session.get(RunModel, run_id)
    if run is None:
        raise WorkflowError("Run not found.")
    if run.status != RunStatus.AWAITING_APPROVAL:
        raise WorkflowError("Run is not awaiting approval.")

    run.status = RunStatus.REVIEW_REQUIRED
    run.current_stage = RunStage.CODER
    run.error_message = "Operator rejected the proposed change set."
    _record_event(session, run, "operator_rejected", note or "Operator rejected the run.")
    session.commit()
    result = get_run(session, run_id)
    assert result is not None
    return result


def abort_run(session: Session, run_id: str, note: Optional[str] = None) -> RunResponse:
    run = session.get(RunModel, run_id)
    if run is None:
        raise WorkflowError("Run not found.")
    if run.status == RunStatus.RUNNING:
        raise WorkflowError("Cannot abort a currently running run.")

    run.status = RunStatus.CANCELLED
    run.error_message = note or "Run cancelled by operator."
    _record_event(session, run, "operator_cancelled", run.error_message)
    session.commit()
    result = get_run(session, run_id)
    assert result is not None
    return result


def retry_run(session: Session, run_id: str, note: Optional[str] = None) -> RunResponse:
    run = session.get(RunModel, run_id)
    if run is None:
        raise WorkflowError("Run not found.")
    if run.status == RunStatus.RUNNING:
        raise WorkflowError("Cannot retry a currently running run.")

    run.status = RunStatus.PENDING
    run.current_stage = RunStage.INTAKE
    run.error_message = None
    run.retry_count = 0
    _record_event(session, run, "operator_retried", note or "Operator retried the run.")
    session.commit()
    result = get_run(session, run_id)
    assert result is not None
    return result


def cleanup_workspace(run_id: str) -> dict[str, object]:
    return cleanup_run_workspace(run_id)


def _to_snapshot_response(
    model: Optional[RunStateSnapshotModel],
) -> Optional[RunStateSnapshotResponse]:
    if model is None:
        return None
    return RunStateSnapshotResponse(
        id=model.id,
        stage=model.stage,
        status=model.status,
        retry_count=model.retry_count,
        payload_json=model.payload_json,
        created_at=model.created_at,
    )
