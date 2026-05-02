from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.api.routes.config import require_api_token
from app.db.session import get_db
from app.schemas.playbook import LessonCreate
from app.services.lesson_service import add_lesson

router = APIRouter(tags=["lessons"])


@router.post(
    "/repo-lessons",
    dependencies=[Depends(require_api_token)],
    status_code=status.HTTP_201_CREATED,
)
def create_lesson(payload: LessonCreate, session: Session = Depends(get_db)) -> dict[str, object]:
    try:
        row = add_lesson(session, payload.repo_key, payload.body, payload.source_run_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"id": row.id, "repo_key": row.repo_key}
