
from typing import Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import RunEventModel, RunModel
from app.schemas.run import RunEventResponse, RunResponse


def get_run(session: Session, run_id: str) -> Optional[RunResponse]:
    model = session.get(RunModel, run_id)
    if model is None:
        return None
    return RunResponse(
        id=model.id,
        task_id=model.task_id,
        status=model.status,
        current_stage=model.current_stage,
        provider_name=model.provider_name,
        error_message=model.error_message,
        created_at=model.created_at,
        updated_at=model.updated_at,
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
