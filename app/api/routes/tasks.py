
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.routes.config import require_api_token
from app.db.session import get_db
from app.providers.registry import get_provider
from app.schemas.task import TaskCreate, TaskCreated
from app.services.orchestration_service import get_orchestration_service
from app.services.task_service import create_task_and_run

router = APIRouter(tags=["tasks"])


@router.post("/tasks", response_model=TaskCreated, dependencies=[Depends(require_api_token)])
def create_task(payload: TaskCreate, session: Session = Depends(get_db)) -> TaskCreated:
    provider = get_provider()
    created = create_task_and_run(session, payload, provider_name=provider.__class__.__name__)
    get_orchestration_service().enqueue_run(created.run_id)
    return created
