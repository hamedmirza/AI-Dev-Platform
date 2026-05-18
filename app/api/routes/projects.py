from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.api.routes.config import require_api_token
from app.db.session import get_db
from app.schemas.project import (
    ProjectCommandResponse,
    ProjectCreate,
    ProjectDetail,
    ProjectMessageCreate,
    ProjectQuestionAnswer,
    ProjectSummary,
)
from app.services.orchestration_service import get_orchestration_service
from app.services.project_service import (
    add_project_message,
    answer_project_question,
    approve_project_plan,
    create_project,
    get_project_detail,
    list_projects,
    start_project_build,
)

router = APIRouter(tags=["projects"], dependencies=[Depends(require_api_token)])


@router.get("/projects", response_model=list[ProjectSummary])
def projects_list(session: Session = Depends(get_db)) -> list[ProjectSummary]:
    return list_projects(session)


@router.post("/projects", response_model=ProjectDetail)
def projects_create(payload: ProjectCreate, session: Session = Depends(get_db)) -> ProjectDetail:
    try:
        return create_project(session, payload)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.get("/projects/{project_id}", response_model=ProjectDetail)
def projects_get(project_id: str, session: Session = Depends(get_db)) -> ProjectDetail:
    try:
        return get_project_detail(session, project_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/projects/{project_id}/messages", response_model=ProjectCommandResponse)
def projects_message(
    project_id: str,
    payload: ProjectMessageCreate,
    session: Session = Depends(get_db),
) -> ProjectCommandResponse:
    try:
        project, run_ids = add_project_message(session, project_id, payload.content)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    for run_id in run_ids:
        get_orchestration_service().enqueue_run(run_id)
    return ProjectCommandResponse(
        project=project,
        message="Message processed.",
        action="message",
        run_id=run_ids[0] if run_ids else None,
        run_ids=run_ids,
    )


@router.post(
    "/projects/{project_id}/questions/{question_id}/answer",
    response_model=ProjectDetail,
)
def projects_answer_question(
    project_id: str,
    question_id: int,
    payload: ProjectQuestionAnswer,
    session: Session = Depends(get_db),
) -> ProjectDetail:
    try:
        return answer_project_question(session, project_id, question_id, payload.answer)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/projects/{project_id}/plan/approve", response_model=ProjectDetail)
def projects_approve_plan(
    project_id: str,
    session: Session = Depends(get_db),
) -> ProjectDetail:
    try:
        return approve_project_plan(session, project_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/projects/{project_id}/start-build", response_model=ProjectCommandResponse)
def projects_start_build(
    project_id: str,
    session: Session = Depends(get_db),
) -> ProjectCommandResponse:
    try:
        project, run_ids = start_project_build(session, project_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    for run_id in run_ids:
        get_orchestration_service().enqueue_run(run_id)
    return ProjectCommandResponse(
        project=project,
        message="Build start command processed.",
        action="start_build",
        run_id=run_ids[0] if run_ids else None,
        run_ids=run_ids,
    )
