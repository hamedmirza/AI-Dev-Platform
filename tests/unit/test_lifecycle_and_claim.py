"""Tests for run-claim race protection and lifecycle UX guards.

These tests guard the specific defects identified by the audit:
- Pending->running claim must be atomic (no duplicate processing).
- safe_mode must behave consistently across UI and API task creation.
- Unsupported provider name must produce a 422 (not 500) from the API.
- Approve must fail with a clear WorkflowError when the workspace is missing.
- Reject must leave the run idle with an actionable error message.
"""

from __future__ import annotations

import threading
from pathlib import Path

import pytest

from app.core.enums import RunStage, RunStatus
from app.core.exceptions import WorkflowError
from app.core.settings import clear_settings_cache
from app.db.models import RunModel, TaskModel
from app.db.session import get_session_factory, init_db
from app.services.orchestration_service import OrchestrationService, reset_orchestration_service
from app.services.run_service import approve_run, cleanup_workspace, reject_run
from tests.unit.test_api import FakeProvider, build_client


@pytest.fixture
def isolated_db(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    db_path = tmp_path / "lifecycle.db"
    monkeypatch.setenv("DB_URL", f"sqlite:///{db_path}")
    monkeypatch.setenv("APP_API_TOKEN", "test-token")
    monkeypatch.setenv("WORKSPACE_ROOT", str(tmp_path / "workspace"))
    monkeypatch.setenv("BACKUP_ROOT", str(tmp_path / "backups"))
    monkeypatch.setenv("APP_SETTINGS_FILE", str(tmp_path / ".env"))
    monkeypatch.setenv("SAFE_MODE", "false")
    clear_settings_cache()
    reset_orchestration_service()
    init_db()
    return db_path


def _make_pending_run(title: str = "Race test run") -> str:
    session = get_session_factory()()
    try:
        task = TaskModel(title=title, request_text="Reproduce claim race")
        session.add(task)
        session.flush()
        run = RunModel(
            task_id=task.id,
            status=RunStatus.PENDING,
            current_stage=RunStage.INTAKE,
            provider_name="fake",
        )
        session.add(run)
        session.commit()
        return run.id
    finally:
        session.close()


def _run_status(run_id: str) -> str:
    session = get_session_factory()()
    try:
        run = session.get(RunModel, run_id)
        assert run is not None
        return str(run.status)
    finally:
        session.close()


def test_claim_pending_run_only_one_worker_wins(isolated_db: Path) -> None:
    """Two concurrent claim attempts on the same pending run: only one succeeds."""
    run_id = _make_pending_run()
    service = OrchestrationService()

    winners: list[bool] = []
    barrier = threading.Barrier(2)

    def attempt_claim() -> None:
        session = get_session_factory()()
        try:
            barrier.wait()
            claimed = service._claim_pending_run(session, run_id)
            winners.append(claimed is not None)
        finally:
            session.close()

    threads = [threading.Thread(target=attempt_claim) for _ in range(2)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=5)

    assert winners.count(True) == 1, (
        f"Exactly one worker must claim the run, got: {winners}"
    )
    assert _run_status(run_id) == RunStatus.RUNNING


def test_claim_skips_non_pending_runs(isolated_db: Path) -> None:
    """Claim returns None for runs already in any non-pending state."""
    run_id = _make_pending_run()
    service = OrchestrationService()

    for non_pending_status in (
        RunStatus.RUNNING,
        RunStatus.AWAITING_APPROVAL,
        RunStatus.BLOCKED,
        RunStatus.COMPLETED,
        RunStatus.CANCELLED,
        RunStatus.FAILED,
        RunStatus.REVIEW_REQUIRED,
    ):
        session = get_session_factory()()
        try:
            run = session.get(RunModel, run_id)
            assert run is not None
            run.status = non_pending_status
            session.commit()
        finally:
            session.close()

        session = get_session_factory()()
        try:
            claimed = service._claim_pending_run(session, run_id)
            assert claimed is None, (
                f"Claim must reject status={non_pending_status} but returned a run."
            )
            run = session.get(RunModel, run_id)
            assert run is not None
            assert str(run.status) == non_pending_status, (
                f"Claim must not mutate status; expected {non_pending_status}, got {run.status}"
            )
        finally:
            session.close()


def test_safe_mode_ui_task_creation_does_not_auto_enqueue(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Legacy POST /ui/tasks under SAFE_MODE leaves the run pending (API parity)."""
    client = build_client(tmp_path, monkeypatch)
    # build_client forces SAFE_MODE=false; override after construction so the
    # task creation request actually runs under safe mode.
    monkeypatch.setenv("SAFE_MODE", "true")
    clear_settings_cache()
    with client:
        login = client.post(
            "/ui/login",
            data={"token": "test-token"},
            follow_redirects=False,
        )
        assert login.status_code == 303

        created = client.post(
            "/ui/tasks",
            data={
                "title": "Safe mode UI run",
                "request_text": "Stay pending under safe mode.",
            },
            follow_redirects=False,
        )
        assert created.status_code == 303
        location = created.headers["location"]
        assert "Safe+mode+is+ON" in location, (
            f"Expected safe-mode messaging in redirect; got {location!r}"
        )

        from urllib.parse import parse_qs, urlparse

        run_id = parse_qs(urlparse(location).query)["created_run_id"][0]
        run_response = client.get(
            f"/api/runs/{run_id}",
            headers={"x-api-token": "test-token"},
        )
        assert run_response.status_code == 200
        assert run_response.json()["status"] == RunStatus.PENDING


def test_unsupported_provider_returns_422_not_500(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The /api/tasks route maps ConfigurationError to 422 instead of 500.

    The route under test is `app.api.routes.tasks.create_task`. We exercise it
    directly with the provider override cleared so the real resolver path runs.
    """
    from fastapi import HTTPException

    from app.api.routes.tasks import create_task
    from app.providers.registry import set_provider_override
    from app.schemas.task import TaskCreate

    # Reuse build_client so DB and env are configured, then drop the FakeProvider
    # override to let resolve_provider run its real validation path.
    client = build_client(tmp_path, monkeypatch, provider=FakeProvider())
    with client:
        set_provider_override(None)
        session = get_session_factory()()
        try:
            payload = TaskCreate(
                title="Bad provider",
                request_text="Should fail provider validation.",
                provider="not-a-real-provider",
            )
            with pytest.raises(HTTPException) as excinfo:
                create_task(payload, session=session)
            assert excinfo.value.status_code == 422
            assert "Unsupported model provider" in str(excinfo.value.detail)
        finally:
            session.close()


def test_approve_fails_when_workspace_missing(isolated_db: Path) -> None:
    run_id = _make_pending_run("Approval guard run")
    session = get_session_factory()()
    try:
        run = session.get(RunModel, run_id)
        assert run is not None
        run.status = RunStatus.AWAITING_APPROVAL
        run.current_stage = RunStage.APPROVAL
        session.commit()
    finally:
        session.close()

    session = get_session_factory()()
    try:
        with pytest.raises(WorkflowError) as excinfo:
            approve_run(session, run_id)
        assert "workspace is missing" in str(excinfo.value)

        run = session.get(RunModel, run_id)
        assert run is not None
        assert str(run.status) == RunStatus.AWAITING_APPROVAL
    finally:
        session.close()


def test_reject_leaves_run_idle_with_actionable_message(isolated_db: Path) -> None:
    run_id = _make_pending_run("Reject UX run")
    session = get_session_factory()()
    try:
        run = session.get(RunModel, run_id)
        assert run is not None
        run.status = RunStatus.AWAITING_APPROVAL
        run.current_stage = RunStage.APPROVAL
        session.commit()
    finally:
        session.close()

    session = get_session_factory()()
    try:
        response = reject_run(session, run_id, note="Not good enough")
        assert response.status == RunStatus.REVIEW_REQUIRED
        assert response.error_message is not None
        assert "press Retry" in response.error_message
    finally:
        session.close()


def test_cleanup_workspace_refuses_while_run_is_running(isolated_db: Path) -> None:
    """Cleanup must not delete a workspace from underneath an active worker.

    The previous behavior `shutil.rmtree`-d the workspace regardless of run
    state. If the worker was mid-stage, that crashed it and corrupted artifacts.
    The service-layer guard refuses cleanup while status is RUNNING and points
    the operator at the safe sequence (abort first, then clean).
    """
    run_id = _make_pending_run("Cleanup guard run")
    session = get_session_factory()()
    try:
        run = session.get(RunModel, run_id)
        assert run is not None
        run.status = RunStatus.RUNNING
        run.current_stage = RunStage.CODER
        session.commit()
    finally:
        session.close()

    session = get_session_factory()()
    try:
        with pytest.raises(WorkflowError) as excinfo:
            cleanup_workspace(session, run_id)
        message = str(excinfo.value)
        assert "still running" in message
        assert "Abort the run first" in message

        run = session.get(RunModel, run_id)
        assert run is not None
        assert str(run.status) == RunStatus.RUNNING, (
            "Cleanup must not mutate run status when it refuses."
        )
    finally:
        session.close()


def test_cleanup_workspace_allowed_in_non_running_states(isolated_db: Path) -> None:
    """Cleanup proceeds for every non-RUNNING status (terminal or paused)."""
    run_id = _make_pending_run("Cleanup non-running run")
    safe_statuses = (
        RunStatus.PENDING,
        RunStatus.REVIEW_REQUIRED,
        RunStatus.BLOCKED,
        RunStatus.AWAITING_APPROVAL,
        RunStatus.CANCELLED,
        RunStatus.FAILED,
        RunStatus.COMPLETED,
    )
    for status in safe_statuses:
        session = get_session_factory()()
        try:
            run = session.get(RunModel, run_id)
            assert run is not None
            run.status = status
            session.commit()
        finally:
            session.close()

        session = get_session_factory()()
        try:
            result = cleanup_workspace(session, run_id)
            assert "removed" in result, (
                f"Cleanup must return a result dict for status={status}, got {result!r}"
            )
        finally:
            session.close()
