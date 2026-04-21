
from sqlalchemy.orm import Session

from app.core.enums import RunStage, RunStatus
from app.db.models import RunEventModel, RunModel, TaskModel
from app.schemas.task import TaskCreate, TaskCreated


def create_task_and_run(session: Session, payload: TaskCreate, provider_name: str) -> TaskCreated:
    task = TaskModel(title=payload.title, request_text=payload.to_prompt_text())
    session.add(task)
    session.flush()

    run = RunModel(
        task_id=task.id,
        status=RunStatus.PENDING,
        current_stage=RunStage.INTAKE,
        provider_name=provider_name,
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
    return TaskCreated(task_id=task.id, run_id=run.id, created_at=run.created_at)
