
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.api.routes.config import require_api_token
from app.core.exceptions import ConfigurationError
from app.core.settings import get_settings
from app.db.session import get_db
from app.providers.registry import resolve_provider
from app.schemas.task import TaskCreate, TaskCreated
from app.services.orchestration_service import get_orchestration_service
from app.services.task_service import create_task_and_run

router = APIRouter(tags=["tasks"])


@router.post("/tasks", response_model=TaskCreated, dependencies=[Depends(require_api_token)])
def create_task(payload: TaskCreate, session: Session = Depends(get_db)) -> TaskCreated:
    try:
        provider = resolve_provider(payload.provider, payload.model)
    except ConfigurationError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    created = create_task_and_run(
        session,
        payload,
        provider_name=payload.provider or provider.__class__.__name__,
    )
    if not get_settings().safe_mode:
        get_orchestration_service().enqueue_run(created.run_id)
    return created
