"""Cross-run repo-scoped lesson snippets (Part I)."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.settings import get_settings
from app.db.models import RepoLessonModel


def load_lessons_prompt_prefix(session: Session, repo_key: str) -> str:
    if repo_key == "global":
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
    lines = [f"- {r.body.strip()}" for r in rows if r.body and r.body.strip()]
    if not lines:
        return ""
    prefix = "Prior lessons for this app (do not repeat mistakes; do not expose secrets):\n"
    return prefix + "\n".join(lines) + "\n\n"


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
