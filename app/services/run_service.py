
import json
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import exists, select
from sqlalchemy.orm import Session, selectinload

from app.core.enums import RunStage, RunStatus
from app.core.exceptions import WorkflowError
from app.db.models import RunEventModel, RunModel, RunStateSnapshotModel, TaskModel
from app.schemas.run import (
    RunEventResponse,
    RunHistoryCleanupResponse,
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
    return _to_run_response(model, latest_state_model)


def list_runs(session: Session, limit: int = 12) -> list[RunResponse]:
    bounded_limit = max(1, min(limit, 100))
    models = session.scalars(
        select(RunModel)
        .options(selectinload(RunModel.task))
        .order_by(RunModel.created_at.desc())
        .limit(bounded_limit)
    ).all()
    return [_to_run_response(item, _latest_state(session, item.id)) for item in models]


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
    _record_action_snapshot(session, run, "operator_approved")
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
    _record_action_snapshot(session, run, "operator_rejected")
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
    _record_action_snapshot(session, run, "operator_cancelled")
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
    _record_action_snapshot(session, run, "operator_retried")
    session.commit()
    result = get_run(session, run_id)
    assert result is not None
    return result


def cleanup_workspace(run_id: str) -> dict[str, object]:
    return cleanup_run_workspace(run_id)


def clear_terminal_run_history(
    session: Session,
    *,
    keep_latest: int = 4,
    cleanup_workspaces: bool = True,
) -> RunHistoryCleanupResponse:
    terminal_statuses = [
        RunStatus.COMPLETED,
        RunStatus.FAILED,
        RunStatus.BLOCKED,
        RunStatus.CANCELLED,
    ]
    keep_count = max(0, min(keep_latest, 50))
    terminal_runs = session.scalars(
        select(RunModel)
        .where(RunModel.status.in_(terminal_statuses))
        .order_by(RunModel.updated_at.desc(), RunModel.created_at.desc())
    ).all()
    kept_runs = terminal_runs[:keep_count]
    runs_to_delete = terminal_runs[keep_count:]
    cleaned_workspaces = 0

    for run in runs_to_delete:
        if cleanup_workspaces:
            cleanup_result = cleanup_run_workspace(run.id)
            if bool(cleanup_result.get("removed")):
                cleaned_workspaces += 1
        session.delete(run)

    deleted_runs = len(runs_to_delete)
    session.flush()

    orphan_tasks = session.scalars(
        select(TaskModel).where(~exists().where(RunModel.task_id == TaskModel.id))
    ).all()
    for task in orphan_tasks:
        session.delete(task)

    deleted_tasks = len(orphan_tasks)
    session.commit()
    return RunHistoryCleanupResponse(
        deleted_runs=deleted_runs,
        deleted_tasks=deleted_tasks,
        cleaned_workspaces=cleaned_workspaces,
        kept_terminal_runs=len(kept_runs),
        message=(
            f"Cleared {deleted_runs} terminal runs and kept the latest "
            f"{len(kept_runs)} terminal records."
        ),
    )


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


def _latest_state(session: Session, run_id: str) -> Optional[RunStateSnapshotModel]:
    return session.scalars(
        select(RunStateSnapshotModel)
        .where(RunStateSnapshotModel.run_id == run_id)
        .order_by(RunStateSnapshotModel.id.desc())
        .limit(1)
    ).first()


def _record_action_snapshot(session: Session, run: RunModel, current_step: str) -> None:
    session.add(
        RunStateSnapshotModel(
            run_id=run.id,
            stage=run.current_stage,
            status=run.status,
            retry_count=run.retry_count,
            payload_json=json.dumps(
                {
                    "state": {
                        "run_id": run.id,
                        "task_id": run.task_id,
                        "stage": run.current_stage,
                        "status": run.status,
                        "retry_count": run.retry_count,
                        "error_message": run.error_message or "",
                        "current_step": current_step,
                    }
                },
                indent=2,
            ),
        )
    )


def _to_run_response(
    model: RunModel,
    latest_state_model: Optional[RunStateSnapshotModel],
) -> RunResponse:
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
        created_at_human=_humanize_datetime(model.created_at),
        updated_at_human=_humanize_datetime(model.updated_at),
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
            created_at=model.task.created_at,
            created_at_human=_humanize_datetime(model.task.created_at),
        ),
        latest_state=_to_snapshot_response(latest_state_model),
    )


def _humanize_datetime(value: datetime) -> str:
    current = value
    if current.tzinfo is None:
        current = current.replace(tzinfo=timezone.utc)
    now = datetime.now(timezone.utc)
    seconds = max(0, int((now - current.astimezone(timezone.utc)).total_seconds()))
    if seconds < 60:
        return "just now"
    minutes = seconds // 60
    if minutes < 60:
        return f"{minutes} minute{'s' if minutes != 1 else ''} ago"
    hours = minutes // 60
    if hours < 24:
        return f"{hours} hour{'s' if hours != 1 else ''} ago"
    days = hours // 24
    if days < 7:
        return f"{days} day{'s' if days != 1 else ''} ago"
    return current.astimezone(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
