from __future__ import annotations

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.core.enums import RunStage
from app.core.settings import clear_settings_cache
from app.db.models import Base, RepoLessonModel
from app.services.lesson_service import (
    merge_retry_feedback,
    persist_failure_lessons,
    stage_receives_repo_lessons,
)


@pytest.fixture
def lesson_session() -> Session:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine)
    session = factory()
    try:
        yield session
    finally:
        session.close()


def test_merge_retry_feedback_accumulates_and_dedupes() -> None:
    clear_settings_cache()
    first = merge_retry_feedback([], ["PatchGuardError on routes", "mypy failed"])
    second = merge_retry_feedback(first, ["PatchGuardError on routes", "pytest failed"])
    assert first == ["PatchGuardError on routes", "mypy failed"]
    assert second == ["PatchGuardError on routes", "mypy failed", "pytest failed"]


def test_stage_receives_repo_lessons_for_pipeline_agents() -> None:
    assert stage_receives_repo_lessons(RunStage.CODER)
    assert stage_receives_repo_lessons(RunStage.PLANNER)
    assert not stage_receives_repo_lessons(RunStage.APPROVAL)


def test_persist_failure_lessons_dedupes_and_respects_cap(
    lesson_session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("REPO_LESSON_AUTO_MAX_PER_EVENT", "2")
    clear_settings_cache()
    repo_key = "test-repo-key"
    created = persist_failure_lessons(
        lesson_session,
        repo_key,
        "run-1",
        ["Error A", "Error B", "Error C"],
        source_label="tests_failed",
    )
    lesson_session.commit()
    assert created == 2
    rows = lesson_session.query(RepoLessonModel).filter_by(repo_key=repo_key).all()
    assert len(rows) == 2

    created_again = persist_failure_lessons(
        lesson_session,
        repo_key,
        "run-1",
        ["Error A"],
        source_label="tests_failed",
    )
    lesson_session.commit()
    assert created_again == 0
    assert lesson_session.query(RepoLessonModel).filter_by(repo_key=repo_key).count() == 2
