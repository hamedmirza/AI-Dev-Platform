
import json

from sqlalchemy.orm import Session

from app.core.enums import RunStage, RunStatus
from app.core.request_context import get_request_id
from app.db.models import RunEventModel, RunModel, TaskModel
from app.schemas.task import TaskCreate, TaskCreated


def create_task_and_run(session: Session, payload: TaskCreate, provider_name: str) -> TaskCreated:
    request_id = get_request_id()
    stage_models_json = json.dumps(payload.stage_models or {}, sort_keys=True)
    task = TaskModel(
        title=payload.title,
        request_text=payload.to_prompt_text(),
        description=payload.description or payload.request_text,
        workspace_path=payload.workspace_path,
        task_type=payload.task_type,
        constraints_json=json.dumps(payload.constraints),
        target_files_json=json.dumps(payload.target_files),
        provider_override=payload.provider,
        model_override=payload.model,
        source_repo_spec=payload.source_repo,
        use_scout=payload.use_scout,
        stage_models_json=stage_models_json,
        validation_profile=payload.validation_profile,
        validation_commands_json=json.dumps(payload.validation_commands),
    )
    session.add(task)
    session.flush()

    run = RunModel(
        task_id=task.id,
        status=RunStatus.PENDING,
        current_stage=RunStage.INTAKE,
        provider_name=provider_name,
        request_id=request_id,
        validation_profile=payload.validation_profile,
    )
    session.add(run)
    session.flush()

    session.add(
        RunEventModel(
            run_id=run.id,
            event_type="run_created",
            message="Run created and marked pending for processing.",
            payload_json=None,
        )
    )
    session.commit()
    return TaskCreated(
        task_id=task.id,
        run_id=run.id,
        request_id=request_id,
        created_at=run.created_at,
    )
