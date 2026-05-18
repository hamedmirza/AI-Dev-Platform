import json
import re
from typing import Optional

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.core.enums import RunStatus
from app.core.exceptions import ConfigurationError
from app.core.settings import get_settings
from app.db.models import (
    ProjectBuildItemModel,
    ProjectMessageModel,
    ProjectModel,
    ProjectQuestionModel,
    RunModel,
    utc_now,
)
from app.providers.registry import resolve_provider
from app.schemas.project import (
    ProjectBuildItemResponse,
    ProjectCreate,
    ProjectDetail,
    ProjectMessageResponse,
    ProjectQuestionResponse,
    ProjectSummary,
)
from app.schemas.task import TaskCreate
from app.services.source_repo_policy import repo_key_for_source_spec, validate_source_repo_spec
from app.services.task_service import create_task_and_run

REQUIRED_QUESTIONS: list[tuple[str, str, str, list[str]]] = [
    (
        "users",
        "Who are the primary users, and what jobs do they need this app to handle?",
        "Defines workflow priority, permissions, and UI density.",
        [],
    ),
    (
        "workflows",
        "What are the must-have workflows for the first usable version?",
        "Prevents the agents from inventing scope or building the wrong screens.",
        [],
    ),
    (
        "data",
        "What core data entities should the app store and relate?",
        "Required before backend schema, API routes, and UI forms are planned.",
        [],
    ),
    (
        "auth",
        "What authentication and roles are required for the first version?",
        "Controls security model, route protection, and audit requirements.",
        ["No auth for local prototype", "Single operator", "Multi-user roles"],
    ),
    (
        "stack",
        "What stack should be used, or should the platform choose the default?",
        "Validation and file ownership depend on the stack.",
        ["FastAPI + React/Vite + SQLite", "Backend only", "Frontend only"],
    ),
    (
        "validation",
        "Which checks must pass before you consider the app ready?",
        "Local validation is the source of truth for agent completion.",
        ["ruff + mypy + pytest", "frontend typecheck + build", "full-stack gates"],
    ),
    (
        "deployment",
        "Where should this app run first?",
        "Avoids hidden assumptions about local ports, Docker, or remote deployment.",
        ["Local only", "Docker local", "GitHub/remote later"],
    ),
]


def create_project(session: Session, payload: ProjectCreate) -> ProjectDetail:
    if payload.source_repo:
        try:
            validate_source_repo_spec(payload.source_repo, get_settings())
        except ConfigurationError as exc:
            raise ValueError(str(exc)) from exc
    slug = _slugify(payload.name)
    project = ProjectModel(
        name=payload.name,
        slug=slug,
        initial_requirements=payload.initial_requirements,
        source_repo_spec=payload.source_repo,
        repo_key=repo_key_for_source_spec(payload.source_repo),
        status="intake",
        app_type=payload.app_type,
        validation_profile=payload.validation_profile,
        validation_commands_json=json.dumps(payload.validation_commands),
    )
    session.add(project)
    session.flush()
    _add_message(
        session,
        project.id,
        "user",
        "requirement",
        payload.initial_requirements,
        {"source": "initial_requirements"},
    )
    _add_message(
        session,
        project.id,
        "assistant",
        "status",
        (
            "I created the project workspace. I will ask the missing product and "
            "delivery questions before starting implementation."
        ),
        {"status": "intake"},
    )
    _ensure_questions(session, project)
    _recalculate_project_state(project)
    session.commit()
    return get_project_detail(session, project.id)


def list_projects(session: Session) -> list[ProjectSummary]:
    projects = session.scalars(
        select(ProjectModel)
        .options(
            selectinload(ProjectModel.questions),
            selectinload(ProjectModel.build_items),
        )
        .order_by(ProjectModel.updated_at.desc(), ProjectModel.created_at.desc())
    ).all()
    for project in projects:
        _sync_build_item_statuses(session, project)
    return [_to_project_summary(project) for project in projects]


def get_project_detail(session: Session, project_id: str) -> ProjectDetail:
    project = _get_project(session, project_id)
    _sync_build_item_statuses(session, project)
    return _to_project_detail(project)


def add_project_message(
    session: Session,
    project_id: str,
    content: str,
) -> tuple[ProjectDetail, list[str]]:
    project = _get_project(session, project_id)
    text = content.strip()
    _add_message(session, project.id, "user", _classify_message(text), text, {})
    lower = text.lower()
    run_ids: list[str] = []

    if _is_approve_command(lower):
        approve_project_plan(session, project.id)
        return get_project_detail(session, project.id), []
    if _is_plan_command(lower):
        _handle_plan_command(session, project)
    elif _is_start_command(lower):
        run_ids = _handle_start_command(session, project)
    elif _is_pause_command(lower):
        project.status = "blocked"
        _add_message(
            session,
            project.id,
            "assistant",
            "status",
            (
                "Project work is paused. Say `resume` or `start build` when you "
                "want agents to continue."
            ),
            {"command": "pause"},
        )
    elif _is_status_command(lower):
        _add_status_message(session, project)
    else:
        _apply_freeform_answer(session, project, text)

    _recalculate_project_state(project)
    session.commit()
    return get_project_detail(session, project.id), run_ids


def answer_project_question(
    session: Session,
    project_id: str,
    question_id: int,
    answer: str,
) -> ProjectDetail:
    project = _get_project(session, project_id)
    question = session.get(ProjectQuestionModel, question_id)
    if question is None or question.project_id != project.id:
        raise ValueError("Question not found for this project.")
    question.answer = answer.strip()
    question.status = "answered"
    question.answered_at = utc_now()
    _add_message(
        session,
        project.id,
        "user",
        "answer",
        f"{question.question}\n\nAnswer: {question.answer}",
        {"question_id": question.id, "key": question.key},
    )
    _add_message(
        session,
        project.id,
        "assistant",
        "status",
        _next_question_or_ready(project),
        {"readiness_score": _readiness_score(project)},
    )
    _recalculate_project_state(project)
    session.commit()
    return get_project_detail(session, project.id)


def approve_project_plan(session: Session, project_id: str) -> ProjectDetail:
    project = _get_project(session, project_id)
    _ensure_build_items(session, project)
    for item in project.build_items:
        if item.status == "draft":
            item.status = "approved"
    project.status = "ready_for_approval"
    _add_message(
        session,
        project.id,
        "assistant",
        "decision",
        "Build plan approved. You can now start the eligible scoped agent runs.",
        {"action": "approve_plan"},
    )
    session.commit()
    return get_project_detail(session, project.id)


def start_project_build(session: Session, project_id: str) -> tuple[ProjectDetail, list[str]]:
    project = _get_project(session, project_id)
    _sync_build_item_statuses(session, project)
    if _readiness_score(project) < 100:
        _add_message(
            session,
            project.id,
            "assistant",
            "question",
            "I need the open questions answered before implementation starts.",
            {"open_questions": [q.key for q in project.questions if q.status == "open"]},
        )
        session.commit()
        return get_project_detail(session, project.id), []

    _ensure_build_items(session, project)
    _sync_build_item_statuses(session, project)
    eligible_items = _eligible_build_items(project)
    if not eligible_items:
        pending_dependencies = _blocked_by_dependencies(project)
        message = (
            "No new build items are eligible to start. Approve or complete the active linked "
            "runs, then start agents again."
            if pending_dependencies
            else "All build items already have linked runs."
        )
        _add_message(
            session,
            project.id,
            "assistant",
            "status",
            message,
            {"blocked_items": pending_dependencies},
        )
        session.commit()
        return get_project_detail(session, project.id), []

    provider = resolve_provider(None, None)
    run_ids: list[str] = []
    started_items: list[str] = []
    for item in eligible_items:
        task_payload = TaskCreate(
            title=f"{project.name}: {item.title}",
            description=item.description,
            request_text=_task_request_from_project(project, item),
            task_type=item.item_type,
            target_files=item.target_files,
            constraints=[
                "Use the approved project requirements and decisions.",
                "Ask for clarification by blocking rather than inventing missing scope.",
                "Keep changes inside this build item scope.",
                (
                    "This is one subagent in a project-level parallel orchestration. Do not "
                    "change files outside your assigned target_files or assume another "
                    "subagent's unapproved work is already merged."
                ),
            ],
            source_repo=project.source_repo_spec,
            validation_profile=project.validation_profile or "auto",
            validation_commands=_json_list(project.validation_commands_json),
        )
        created = create_task_and_run(
            session,
            task_payload,
            provider_name=provider.__class__.__name__,
        )
        item.run_id = created.run_id
        item.status = "queued"
        run_ids.append(created.run_id)
        started_items.append(item.title)
    project.status = "building"
    _add_message(
        session,
        project.id,
        "assistant",
        "command",
        f"Started {len(run_ids)} parallel scoped agent run(s): {', '.join(started_items)}.",
        {
            "run_ids": run_ids,
            "build_item_ids": [item.id for item in eligible_items],
            "parallel": len(run_ids) > 1,
        },
    )
    session.commit()
    return get_project_detail(session, project.id), run_ids


def _get_project(session: Session, project_id: str) -> ProjectModel:
    project = session.scalars(
        select(ProjectModel)
        .options(
            selectinload(ProjectModel.messages),
            selectinload(ProjectModel.questions),
            selectinload(ProjectModel.build_items),
        )
        .where(ProjectModel.id == project_id)
        .execution_options(populate_existing=True)
    ).first()
    if project is None:
        raise ValueError("Project not found.")
    return project


def _ensure_questions(session: Session, project: ProjectModel) -> None:
    existing = {question.key for question in project.questions}
    for key, question, reason, options in REQUIRED_QUESTIONS:
        if key in existing:
            continue
        session.add(
            ProjectQuestionModel(
                project_id=project.id,
                key=key,
                question=question,
                reason=reason,
                options_json=json.dumps(options),
            )
        )
    session.flush()


def _handle_plan_command(session: Session, project: ProjectModel) -> None:
    if _readiness_score(project) < 100:
        _add_message(
            session,
            project.id,
            "assistant",
            "question",
            "I cannot create a responsible build plan yet. Please answer the open questions first.",
            {"open_questions": [q.key for q in project.questions if q.status == "open"]},
        )
        return
    _ensure_build_items(session, project)
    project.status = "ready_for_approval"
    _add_message(
        session,
        project.id,
        "assistant",
        "decision",
        "I drafted a scoped build plan. Review the build items and say `approve plan` to continue.",
        {"build_items": [item.title for item in project.build_items]},
    )


def _handle_start_command(session: Session, project: ProjectModel) -> list[str]:
    if "approve" in project.status or project.status == "ready_for_approval":
        detail, run_ids = start_project_build(session, project.id)
        project.status = detail.status
        if run_ids:
            return run_ids
    if not project.build_items:
        _handle_plan_command(session, project)
        return []
    _add_message(
        session,
        project.id,
        "assistant",
        "decision",
        "Say `approve plan` first so I have explicit permission to start agent work.",
        {"status": project.status},
    )
    return []


def _ensure_build_items(session: Session, project: ProjectModel) -> None:
    if project.build_items:
        return
    items: list[tuple[str, str, str, list[str], list[str]]] = [
        (
            "Product and architecture baseline",
            (
                "Create or update project docs: product scope, architecture, "
                "data model, and validation profile."
            ),
            "planner",
            ["docs/"],
            [],
        ),
        (
            "Backend foundation",
            (
                "Implement the backend skeleton, persistence model, API routes, "
                "and tests required by the approved scope."
            ),
            "backend_coder",
            ["app/", "tests/"],
            [],
        ),
        (
            "Frontend operator experience",
            (
                "Implement the initial screens, navigation, states, and responsive "
                "UI for the approved workflows."
            ),
            "frontend_coder",
            ["frontend/"],
            [],
        ),
        (
            "Release validation",
            "Run project validation gates, collect evidence, and prepare final approval notes.",
            "tester",
            ["."],
            [
                "Product and architecture baseline",
                "Backend foundation",
                "Frontend operator experience",
            ],
        ),
    ]
    for title, description, role, target_files, depends_on in items:
        session.add(
            ProjectBuildItemModel(
                project_id=project.id,
                title=title,
                description=description,
                assigned_role=role,
                target_files_json=json.dumps(target_files),
                depends_on_json=json.dumps(depends_on),
            )
        )
    session.flush()


def _eligible_build_items(project: ProjectModel) -> list[ProjectBuildItemModel]:
    completed_titles = _dependency_satisfied_titles(project)
    return [
        item
        for item in sorted(project.build_items, key=lambda row: row.id)
        if item.status == "approved"
        and not item.run_id
        and all(dependency in completed_titles for dependency in item.depends_on)
    ]


def _dependency_satisfied_titles(project: ProjectModel) -> set[str]:
    return {
        item.title
        for item in project.build_items
        if item.status in {"awaiting_approval", "completed"}
    }


def _blocked_by_dependencies(project: ProjectModel) -> list[str]:
    completed_titles = _dependency_satisfied_titles(project)
    blocked: list[str] = []
    for item in sorted(project.build_items, key=lambda row: row.id):
        if item.status != "approved" or item.run_id:
            continue
        missing = [
            dependency
            for dependency in item.depends_on
            if dependency not in completed_titles
        ]
        if missing:
            blocked.append(f"{item.title}: waiting for {', '.join(missing)}")
    return blocked


def _sync_build_item_statuses(session: Session, project: ProjectModel) -> None:
    run_ids = [item.run_id for item in project.build_items if item.run_id]
    if not run_ids:
        _recalculate_project_state(project)
        return

    runs = {
        run.id: run
        for run in session.scalars(select(RunModel).where(RunModel.id.in_(run_ids))).all()
    }
    for item in project.build_items:
        if not item.run_id:
            continue
        run = runs.get(item.run_id)
        if run is None:
            item.status = "missing_run"
            continue
        if run.status in {RunStatus.PENDING, "queued"}:
            item.status = "queued"
        elif run.status == RunStatus.RUNNING:
            item.status = "running"
        elif run.status == RunStatus.AWAITING_APPROVAL:
            item.status = "awaiting_approval"
        elif run.status == RunStatus.REVIEW_REQUIRED:
            item.status = "review_required"
        elif run.status == RunStatus.COMPLETED:
            item.status = "completed"
        elif run.status in {RunStatus.BLOCKED, RunStatus.FAILED, RunStatus.CANCELLED}:
            item.status = run.status

    item_statuses = {item.status for item in project.build_items}
    active_statuses = {"queued", "running", "awaiting_approval", "review_required"}
    broken_statuses = {"blocked", "failed", "cancelled", "missing_run"}
    if any(status in active_statuses for status in item_statuses):
        project.status = "building"
    elif project.build_items and all(item.status == "completed" for item in project.build_items):
        project.status = "completed"
    elif any(status in broken_statuses for status in item_statuses):
        project.status = "blocked"
    else:
        _recalculate_project_state(project)


def _apply_freeform_answer(session: Session, project: ProjectModel, text: str) -> None:
    open_questions = [q for q in project.questions if q.status == "open"]
    matched = _match_question_from_text(open_questions, text)
    if matched is not None:
        matched.answer = text
        matched.status = "answered"
        matched.answered_at = utc_now()
        _add_message(
            session,
            project.id,
            "assistant",
            "status",
            _next_question_or_ready(project),
            {"answered_question": matched.key},
        )
        return
    _add_message(
        session,
        project.id,
        "assistant",
        "question",
        _next_question_or_ready(project),
        {"open_questions": [q.key for q in open_questions]},
    )


def _match_question_from_text(
    open_questions: list[ProjectQuestionModel],
    text: str,
) -> Optional[ProjectQuestionModel]:
    lower = text.lower()
    for question in open_questions:
        if lower.startswith(f"{question.key}:") or lower.startswith(f"{question.key} -"):
            return question
    if len(open_questions) == 1:
        return open_questions[0]
    return None


def _next_question_or_ready(project: ProjectModel) -> str:
    open_questions = [q for q in project.questions if q.status == "open"]
    if not open_questions:
        return "All intake questions are answered. Say `create plan` when you want the build plan."
    next_question = open_questions[0]
    return f"Next question: {next_question.question}"


def _add_status_message(session: Session, project: ProjectModel) -> None:
    open_count = len([q for q in project.questions if q.status == "open"])
    running_count = len([i for i in project.build_items if i.status in {"queued", "running"}])
    _add_message(
        session,
        project.id,
        "assistant",
        "status",
        (
            f"Project is `{project.status}` with readiness {project.readiness_score}%, "
            f"{open_count} open questions, and {running_count} active build items."
        ),
        {
            "status": project.status,
            "readiness_score": project.readiness_score,
            "open_questions": open_count,
            "active_build_items": running_count,
        },
    )


def _task_request_from_project(project: ProjectModel, item: ProjectBuildItemModel) -> str:
    answers = "\n".join(
        f"- {question.key}: {question.answer}"
        for question in project.questions
        if question.answer
    )
    return "\n".join(
        [
            f"Project: {project.name}",
            f"Project status: {project.status}",
            "Initial requirements:",
            project.initial_requirements,
            "Confirmed intake answers:",
            answers or "- none",
            "Build item:",
            item.title,
            item.description,
        ]
    )


def _classify_message(text: str) -> str:
    lower = text.lower().strip()
    if _is_plan_command(lower) or _is_start_command(lower) or _is_pause_command(lower):
        return "command"
    if _is_status_command(lower):
        return "status"
    return "answer"


def _is_plan_command(lower: str) -> bool:
    return lower in {"create plan", "plan", "generate plan", "draft plan"}


def _is_approve_command(lower: str) -> bool:
    return lower in {"approve plan", "approve build plan", "plan approved"}


def _is_start_command(lower: str) -> bool:
    return lower in {"start", "start build", "run agents", "spin off agents", "resume"}


def _is_pause_command(lower: str) -> bool:
    return lower in {"pause", "pause agents", "stop agents"}


def _is_status_command(lower: str) -> bool:
    return lower in {"status", "where are we", "progress"}


def _readiness_score(project: ProjectModel) -> int:
    total = len(project.questions)
    if total == 0:
        return 0
    answered = len([q for q in project.questions if q.status == "answered"])
    return int((answered / total) * 100)


def _recalculate_project_state(project: ProjectModel) -> None:
    project.readiness_score = _readiness_score(project)
    if project.status in {
        "ready_for_approval",
        "building",
        "blocked",
        "completed",
        "cancelled",
    }:
        return
    project.status = "planning" if project.readiness_score == 100 else "intake"


def _add_message(
    session: Session,
    project_id: str,
    role: str,
    message_type: str,
    content: str,
    structured: dict[str, object],
) -> None:
    session.add(
        ProjectMessageModel(
            project_id=project_id,
            role=role,
            message_type=message_type,
            content=content,
            structured_json=json.dumps(structured, sort_keys=True),
        )
    )


def _to_project_summary(project: ProjectModel) -> ProjectSummary:
    open_questions = len([q for q in project.questions if q.status == "open"])
    active_runs = len([i for i in project.build_items if i.status in {"queued", "running"}])
    return ProjectSummary(
        id=project.id,
        name=project.name,
        slug=project.slug,
        status=project.status,
        app_type=project.app_type,
        source_repo_spec=project.source_repo_spec,
        validation_profile=project.validation_profile,
        readiness_score=project.readiness_score,
        open_questions=open_questions,
        build_items=len(project.build_items),
        active_runs=active_runs,
        created_at=project.created_at,
        updated_at=project.updated_at,
    )


def _to_project_detail(project: ProjectModel) -> ProjectDetail:
    summary = _to_project_summary(project)
    return ProjectDetail(
        **summary.model_dump(),
        initial_requirements=project.initial_requirements,
        target_stack=_json_dict(project.target_stack_json),
        messages=[
            ProjectMessageResponse(
                id=message.id,
                project_id=message.project_id,
                role=message.role,
                message_type=message.message_type,
                content=message.content,
                structured_json=message.structured_json,
                created_at=message.created_at,
            )
            for message in sorted(project.messages, key=lambda item: item.created_at)
        ],
        questions=[
            ProjectQuestionResponse(
                id=question.id,
                project_id=question.project_id,
                key=question.key,
                question=question.question,
                reason=question.reason,
                answer_type=question.answer_type,
                options=_json_list(question.options_json),
                status=question.status,
                answer=question.answer,
                created_at=question.created_at,
                answered_at=question.answered_at,
            )
            for question in sorted(project.questions, key=lambda item: item.id)
        ],
        build_items_detail=[
            ProjectBuildItemResponse(
                id=item.id,
                project_id=item.project_id,
                parent_id=item.parent_id,
                title=item.title,
                description=item.description,
                item_type=item.item_type,
                status=item.status,
                target_files=item.target_files,
                depends_on=item.depends_on,
                assigned_role=item.assigned_role,
                run_id=item.run_id,
                created_at=item.created_at,
                updated_at=item.updated_at,
            )
            for item in sorted(project.build_items, key=lambda row: row.id)
        ],
    )


def _json_list(raw: str) -> list[str]:
    try:
        value = json.loads(raw)
    except json.JSONDecodeError:
        return []
    if not isinstance(value, list):
        return []
    return [str(item) for item in value]


def _json_dict(raw: str) -> dict[str, str]:
    try:
        value = json.loads(raw)
    except json.JSONDecodeError:
        return {}
    if not isinstance(value, dict):
        return {}
    return {str(key): str(item) for key, item in value.items()}


def _slugify(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    return slug or "project"
