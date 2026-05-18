"""Cross-run repo-scoped lesson snippets and in-run retry feedback memory."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.enums import RunStage
from app.core.settings import get_settings
from app.db.models import RepoLessonModel

RETRY_FEEDBACK_HEADER = (
    "Prior failures and review issues in this run (resolve all; do not repeat mistakes):"
)
LESSON_PROMPT_HEADER = (
    "Prior lessons for this repo/task (do not repeat mistakes; do not expose secrets):"
)

_STAGES_WITH_LESSONS = frozenset(
    {
        RunStage.PLANNER,
        RunStage.ARCHITECT,
        RunStage.UI_DESIGNER,
        RunStage.CODER,
        RunStage.REVIEWER,
        RunStage.TESTER,
    }
)


def stage_receives_repo_lessons(stage: str | RunStage) -> bool:
    normalized = stage.value if isinstance(stage, RunStage) else str(stage)
    try:
        return RunStage(normalized) in _STAGES_WITH_LESSONS
    except ValueError:
        return False


def normalize_feedback_key(text: str) -> str:
    return " ".join(text.split()).lower()


def merge_retry_feedback(
    existing: list[str],
    new_items: list[str],
    *,
    max_items: int | None = None,
) -> list[str]:
    cap = max_items if max_items is not None else get_settings().retry_feedback_max_items
    cap = max(1, min(cap, 100))
    seen = {normalize_feedback_key(item) for item in existing}
    merged = list(existing)
    for raw in new_items:
        item = raw.strip()
        if not item:
            continue
        key = normalize_feedback_key(item)
        if key in seen:
            continue
        seen.add(key)
        merged.append(item)
    if len(merged) > cap:
        merged = merged[-cap:]
    return merged


def format_accumulated_retry_feedback(items: list[str]) -> str:
    if not items:
        return ""
    bullets = "\n".join(f"- {item}" for item in items)
    return f"\n{RETRY_FEEDBACK_HEADER}\n{bullets}"


def load_lessons_prompt_prefix(session: Session, repo_key: str) -> str:
    if not repo_key:
        return ""
    cap = max(1, min(get_settings().repo_lesson_max_lines, 100))
    rows = list(
        session.scalars(
            select(RepoLessonModel)
            .where(RepoLessonModel.repo_key == repo_key)
            .order_by(RepoLessonModel.created_at.desc())
            .limit(cap)
        ).all()
    )
    if not rows:
        return ""
    lines = [f"- {row.body.strip()}" for row in rows if row.body and row.body.strip()]
    if not lines:
        return ""
    return f"{LESSON_PROMPT_HEADER}\n" + "\n".join(lines) + "\n\n"


def _lesson_body_fingerprint(body: str) -> str:
    return normalize_feedback_key(body)[:240]


def _recent_lesson_fingerprints(session: Session, repo_key: str, *, limit: int = 80) -> set[str]:
    rows = session.scalars(
        select(RepoLessonModel.body)
        .where(RepoLessonModel.repo_key == repo_key)
        .order_by(RepoLessonModel.created_at.desc())
        .limit(limit)
    ).all()
    return {_lesson_body_fingerprint(str(body)) for body in rows if body}


def _format_auto_lesson_body(item: str, source_label: str) -> str:
    cleaned = " ".join(item.split())
    if len(cleaned) > 900:
        cleaned = cleaned[:897] + "..."
    label = source_label.strip().replace("_", " ") or "failure"
    return f"[{label}] {cleaned}"[:4000]


def persist_failure_lessons(
    session: Session,
    repo_key: str,
    run_id: str,
    items: list[str],
    *,
    source_label: str,
) -> int:
    settings = get_settings()
    if not settings.auto_persist_failure_lessons or not repo_key:
        return 0
    if not items:
        return 0

    per_event_cap = max(1, min(settings.repo_lesson_auto_max_per_event, 20))
    known = _recent_lesson_fingerprints(session, repo_key)
    created = 0
    for raw in items:
        if created >= per_event_cap:
            break
        body = _format_auto_lesson_body(raw, source_label)
        fingerprint = _lesson_body_fingerprint(body)
        if fingerprint in known:
            continue
        known.add(fingerprint)
        session.add(
            RepoLessonModel(
                repo_key=repo_key,
                body=body,
                source_run_id=run_id,
            )
        )
        created += 1
    return created


def add_lesson(
    session: Session,
    repo_key: str,
    body: str,
    source_run_id: str | None = None,
) -> RepoLessonModel:
    text = body.strip()[:4000]
    if not text:
        raise ValueError("Lesson body is empty.")
    row = RepoLessonModel(repo_key=repo_key, body=text, source_run_id=source_run_id)
    session.add(row)
    session.commit()
    session.refresh(row)
    return row
