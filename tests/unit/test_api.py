import json
import subprocess
import time
from pathlib import Path
from typing import Any, Optional
from urllib.parse import parse_qs, urlparse

from fastapi.testclient import TestClient

from app.core.enums import ProviderStatus
from app.core.settings import clear_settings_cache
from app.providers.base import BaseProvider
from app.providers.registry import set_provider_override
from app.schemas.provider import ProviderHealthResponse
from app.services.orchestration_service import reset_orchestration_service


class FakeProvider(BaseProvider):
    def __init__(self) -> None:
        self.review_failures_remaining = 0
        self.test_failures_remaining = 0

    def invoke_json(self, system_prompt: str, user_prompt: str) -> str:
        payload: dict[str, Any]
        prompt = f"{system_prompt}\n{user_prompt}".lower()
        if "summary, assumptions, risks, steps" in prompt:
            payload = {
                "summary": "Implement the requested backend feature.",
                "assumptions": ["Repository is configured."],
                "risks": ["External provider may fail."],
                "steps": ["Inspect current code", "Propose changes", "Validate outputs"],
                "acceptance_criteria": ["Routes respond", "Artifacts are stored"],
            }
        elif "changed_files" in prompt:
            payload = {
                "changed_files": ["README.md"],
                "implementation_notes": ["Apply a small workspace change."],
                "requires_operator_approval": True,
                "file_changes": [
                    {
                        "path": "README.md",
                        "content": "fixture repo\nupdated by ai\n",
                        "change_type": "upsert",
                    }
                ],
            }
        elif "touched_modules" in prompt:
            payload = {
                "touched_modules": ["app/api", "app/services"],
                "file_change_plan": ["Add API endpoints", "Store artifacts"],
                "dependency_notes": [],
                "migration_notes": [],
            }
        elif "approved" in prompt:
            if self.review_failures_remaining > 0:
                self.review_failures_remaining -= 1
                payload = {
                    "approved": False,
                    "summary": "Change set still needs revision.",
                    "issues": ["Address the unresolved review issue."],
                }
            else:
                payload = {
                    "approved": True,
                    "summary": "Change set is acceptable.",
                    "issues": [],
                }
        else:
            if self.test_failures_remaining > 0:
                self.test_failures_remaining -= 1
                payload = {
                    "passed": False,
                    "summary": "Validation failed on the current proposal.",
                    "commands": ["pytest"],
                    "failures": ["Fix the failing validation case."],
                }
            else:
                payload = {
                    "passed": True,
                    "summary": "Validation strategy accepted.",
                    "commands": ["pytest"],
                    "failures": [],
                }
        return json.dumps(payload)

    def healthcheck(self) -> ProviderHealthResponse:
        return ProviderHealthResponse(
            provider="fake",
            status=ProviderStatus.HEALTHY,
            detail="Fake provider is healthy for tests.",
            model="fake-model",
        )


class SlowPlannerProvider(FakeProvider):
    def invoke_json(self, system_prompt: str, user_prompt: str) -> str:
        prompt = f"{system_prompt}\n{user_prompt}".lower()
        if "summary, assumptions, risks, steps" in prompt:
            time.sleep(0.2)
        return super().invoke_json(system_prompt, user_prompt)


def build_client(
    tmp_path: Path,
    monkeypatch,
    provider: Optional[BaseProvider] = None,
) -> TestClient:
    db_path = tmp_path / "test.db"
    workspace_root = tmp_path / "workspace"
    backup_root = tmp_path / "backups"
    source_repo = tmp_path / "source-repo"
    monkeypatch.setenv("DB_URL", f"sqlite:///{db_path}")
    monkeypatch.setenv("APP_API_TOKEN", "test-token")
    monkeypatch.setenv("WORKSPACE_ROOT", str(workspace_root))
    monkeypatch.setenv("BACKUP_ROOT", str(backup_root))
    monkeypatch.setenv("SOURCE_REPO_PATH", str(source_repo))
    monkeypatch.setenv("APP_SETTINGS_FILE", str(tmp_path / ".env"))

    source_repo.mkdir(parents=True, exist_ok=True)
    subprocess.run(["git", "init", "-b", "main"], cwd=source_repo, check=True, capture_output=True)
    (source_repo / "README.md").write_text("fixture repo\n", encoding="utf-8")
    (source_repo / "tests").mkdir()
    (source_repo / "tests" / "test_smoke.py").write_text(
        "def test_smoke():\n    assert True\n",
        encoding="utf-8",
    )
    subprocess.run(
        ["git", "add", "README.md", "tests"],
        cwd=source_repo,
        check=True,
        capture_output=True,
    )
    subprocess.run(
        [
            "git",
            "-c",
            "user.name=Test User",
            "-c",
            "user.email=test@example.com",
            "commit",
            "-m",
            "Initial commit",
        ],
        cwd=source_repo,
        check=True,
        capture_output=True,
    )

    clear_settings_cache()
    reset_orchestration_service()
    set_provider_override(provider or FakeProvider())

    from app.api.main import create_app

    return TestClient(create_app())


def wait_for_run_status(
    client: TestClient,
    run_id: str,
    headers: dict[str, str],
    expected_statuses: set[str],
) -> str:
    status = ""
    for _ in range(60):
        run_response = client.get(f"/api/runs/{run_id}", headers=headers)
        assert run_response.status_code == 200
        status = run_response.json()["status"]
        if status in expected_statuses:
            return status
        time.sleep(0.05)
    raise AssertionError(
        f"Run {run_id} did not reach one of {expected_statuses}; last status={status}"
    )


def test_health_endpoint(tmp_path: Path, monkeypatch) -> None:
    client = build_client(tmp_path, monkeypatch)
    with client:
        response = client.get("/api/health")
        assert response.status_code == 200
        assert response.json() == {"status": "ok"}
        assert response.headers["x-request-id"]

        provider = client.get("/api/health/provider")
        assert provider.status_code == 200
        assert provider.json()["status"] == "healthy"

        repository = client.get("/api/health/repository")
        assert repository.status_code == 200
        assert repository.json()["path"].endswith("source-repo")

        github = client.get("/api/health/github")
        assert github.status_code == 200
        assert github.json()["configured"] is False


def test_task_run_reaches_awaiting_approval(tmp_path: Path, monkeypatch) -> None:
    client = build_client(tmp_path, monkeypatch)
    headers = {"x-api-token": "test-token"}

    with client:
        response = client.post(
            "/api/tasks",
            headers=headers,
            json={
                "title": "Implement backend runtime",
                "request_text": (
                    "Build the API surface and persist run artifacts for operator review."
                ),
            },
        )
        assert response.status_code == 200
        created = response.json()
        assert response.headers["x-request-id"]
        assert created["request_id"] == response.headers["x-request-id"]

        run_id = created["run_id"]
        status = wait_for_run_status(
            client,
            run_id,
            headers,
            {"awaiting_approval", "failed", "review_required", "blocked"},
        )
        assert status == "awaiting_approval"

        history = client.get(f"/api/runs/{run_id}/history", headers=headers)
        assert history.status_code == 200
        assert any(item["event_type"] == "awaiting_approval" for item in history.json())

        run_summary = client.get(f"/api/runs/{run_id}", headers=headers)
        assert run_summary.status_code == 200
        assert run_summary.json()["task"]["title"] == "Implement backend runtime"
        assert run_summary.json()["request_id"] == created["request_id"]
        assert run_summary.json()["latest_state"] is not None

        snapshots = client.get(f"/api/runs/{run_id}/state-snapshots", headers=headers)
        assert snapshots.status_code == 200
        assert any(item["stage"] == "planner" for item in snapshots.json())

        artifacts = client.get(f"/api/runs/{run_id}/artifacts", headers=headers)
        assert artifacts.status_code == 200
        artifact_types = {item["artifact_type"] for item in artifacts.json()}
        assert {"plan", "architecture", "code_change", "review", "test_result", "log"}.issubset(
            artifact_types
        )

        history_events = [item["event_type"] for item in history.json()]
        assert "code_patch_applied" in history_events
        assert "validation_commands_completed" in history_events

        workspace_file = tmp_path / "workspace" / f"run-{run_id}" / "README.md"
        assert workspace_file.read_text(encoding="utf-8") == "fixture repo\nupdated by ai\n"

        workspace_file.write_text("fixture repo\nmodified\n", encoding="utf-8")

        diff = client.get(f"/api/runs/{run_id}/diff", headers=headers)
        assert diff.status_code == 200
        assert diff.json()["has_changes"] is True
        assert "README.md" in "\n".join(diff.json()["changed_files"])
        assert diff.json()["branch"] == f"run/{run_id}"

        files = client.get(f"/api/runs/{run_id}/workspace/files", headers=headers)
        assert files.status_code == 200
        assert "README.md" in files.json()["files"]

        updated = client.post(
            f"/api/runs/{run_id}/workspace/file",
            headers=headers,
            json={"path": "README.md", "content": "fixture repo\nsaved via api\n"},
        )
        assert updated.status_code == 200

        read_back = client.get(
            f"/api/runs/{run_id}/workspace/file",
            headers=headers,
            params={"path": "README.md"},
        )
        assert read_back.status_code == 200
        assert "saved via api" in read_back.json()["content"]

        unsafe_write = client.post(
            f"/api/runs/{run_id}/workspace/file",
            headers=headers,
            json={"path": ".git/config", "content": "unsafe"},
        )
        assert unsafe_write.status_code == 409

        cleanup = client.post(f"/api/runs/{run_id}/cleanup-workspace", headers=headers)
        assert cleanup.status_code == 200
        assert cleanup.json()["removed"] is True

        retry = client.post(
            f"/api/runs/{run_id}/retry",
            headers=headers,
            json={"note": "Retry locally"},
        )
        assert retry.status_code == 200
        assert retry.json()["status"] == "pending"


def test_config_requires_authentication(tmp_path: Path, monkeypatch) -> None:
    client = build_client(tmp_path, monkeypatch)
    with client:
        response = client.get("/api/config")
        assert response.status_code == 401


def test_approve_and_backup_flow(tmp_path: Path, monkeypatch) -> None:
    client = build_client(tmp_path, monkeypatch)
    headers = {"x-api-token": "test-token"}

    with client:
        response = client.post(
            "/api/tasks",
            headers=headers,
            json={
                "title": "Prepare approval path",
                "request_text": (
                    "Build a run that reaches operator approval with stored artifacts."
                ),
            },
        )
        assert response.status_code == 200
        run_id = response.json()["run_id"]

        assert (
            wait_for_run_status(client, run_id, headers, {"awaiting_approval", "failed", "blocked"})
            == "awaiting_approval"
        )

        workspace_file = tmp_path / "workspace" / f"run-{run_id}" / "README.md"
        workspace_file.write_text("fixture repo\ncommitted\n", encoding="utf-8")

        approved = client.post(
            f"/api/runs/{run_id}/approve",
            headers=headers,
            json={"note": "Ship it"},
        )
        assert approved.status_code == 200
        assert approved.json()["status"] == "completed"

        diff = client.get(f"/api/runs/{run_id}/diff", headers=headers)
        assert diff.status_code == 200
        assert diff.json()["has_changes"] is False

        backup = client.post("/api/backups/run", headers=headers)
        assert backup.status_code == 200
        backup_payload = backup.json()

        rehearsal = client.post(
            "/api/backups/restore-rehearsal",
            headers=headers,
            params={"manifest_path": backup_payload["manifest_path"]},
        )
        assert rehearsal.status_code == 200
        assert rehearsal.json()["database_restored"] is True


def test_ui_login_dashboard_and_run_detail(tmp_path: Path, monkeypatch) -> None:
    client = build_client(tmp_path, monkeypatch)

    with client:
        login_page = client.get("/ui/login")
        assert login_page.status_code == 200
        assert "Operator Login" in login_page.text

        login = client.post("/ui/login", data={"token": "test-token"}, follow_redirects=False)
        assert login.status_code == 303

        dashboard = client.get("/ui")
        assert dashboard.status_code == 200
        assert "Operator Console" in dashboard.text

        created = client.post(
            "/ui/tasks",
            data={
                "title": "UI initiated run",
                "request_text": "Create a run from the operator console and inspect its status.",
            },
            follow_redirects=False,
        )
        assert created.status_code == 303
        dashboard_location = created.headers["location"]
        assert dashboard_location.startswith("/ui?")
        parsed = parse_qs(urlparse(dashboard_location).query)
        run_id = parsed["created_run_id"][0]
        run_location = f"/ui/runs/{run_id}"

        dashboard_after = client.get(dashboard_location)
        assert dashboard_after.status_code == 200
        assert run_id in dashboard_after.text
        assert "Task created." in dashboard_after.text

        for _ in range(40):
            detail = client.get(run_location)
            assert detail.status_code == 200
            if "awaiting_approval" in detail.text:
                break
            time.sleep(0.05)

        workspace_file = tmp_path / "workspace" / f"run-{run_id}" / "README.md"
        workspace_file.write_text("fixture repo\nui diff\n", encoding="utf-8")

        detail = client.get(run_location)
        assert "Timeline" in detail.text
        assert "Task Metadata" in detail.text
        assert "State Snapshots" in detail.text
        assert "Artifacts" in detail.text
        assert "Code Review Panel" in detail.text
        assert "Workspace Diff" in detail.text
        assert "README.md" in detail.text
        assert "Workspace Files" in detail.text
        assert "<textarea name=\"content\"" in detail.text

        save_file = client.post(
            f"/ui/runs/{run_id}/files/save",
            data={"path": "README.md", "content": "fixture repo\nui saved\n"},
            follow_redirects=False,
        )
        assert save_file.status_code == 303

        settings_page = client.get("/ui/settings")
        assert settings_page.status_code == 200
        assert "Editable Local Settings" in settings_page.text

        saved = client.post(
            "/ui/settings",
            data={
                "APP_HOST": "0.0.0.0",
                "APP_PORT": "8400",
                "APP_API_TOKEN": "test-token",
                "LMSTUDIO_BASE_URL": "http://localhost:1234/v1",
                "LMSTUDIO_MODEL": "qwen2.5-coder-14b-instruct",
                "LMSTUDIO_API_KEY": "lm-studio",
                "PROVIDER_TIMEOUT_SECONDS": "60",
                "SOURCE_REPO_PATH": str(tmp_path / "source-repo"),
                "WORKSPACE_ROOT": str(tmp_path / "workspace"),
                "BACKUP_ROOT": str(tmp_path / "backups"),
                "GIT_AUTHOR_NAME": "Test User",
                "GIT_AUTHOR_EMAIL": "test@example.com",
                "LOG_LEVEL": "INFO",
            },
            follow_redirects=False,
        )
        assert saved.status_code == 303
        saved_page = client.get(saved.headers["location"])
        assert saved_page.status_code == 200
        assert "Settings saved." in saved_page.text


def test_ui_run_actions_do_not_500_on_invalid_state(tmp_path: Path, monkeypatch) -> None:
    client = build_client(tmp_path, monkeypatch)

    with client:
        login = client.post("/ui/login", data={"token": "test-token"}, follow_redirects=False)
        assert login.status_code == 303

        created = client.post(
            "/ui/tasks",
            data={
                "title": "UI action safety run",
                "request_text": "Create run so action buttons can be exercised safely.",
            },
            follow_redirects=False,
        )
        assert created.status_code == 303
        parsed = parse_qs(urlparse(created.headers["location"]).query)
        run_id = parsed["created_run_id"][0]

        approve = client.post(
            f"/ui/runs/{run_id}/approve",
            data={"note": "should not crash"},
            follow_redirects=False,
        )
        assert approve.status_code == 303
        assert "error=" in approve.headers["location"]

        reject = client.post(
            f"/ui/runs/{run_id}/reject",
            data={"note": "should not crash"},
            follow_redirects=False,
        )
        assert reject.status_code == 303
        assert "error=" in reject.headers["location"]

        detail = client.get(approve.headers["location"])
        assert detail.status_code == 200
        assert "Run is not awaiting approval." in detail.text

        approve_get = client.get(f"/ui/runs/{run_id}/approve", follow_redirects=False)
        assert approve_get.status_code == 303
        reject_get = client.get(f"/ui/runs/{run_id}/reject", follow_redirects=False)
        assert reject_get.status_code == 303
        approve_alias = client.get(f"/runs/{run_id}/approve", follow_redirects=False)
        assert approve_alias.status_code == 303
        reject_alias = client.get(f"/runs/{run_id}/reject", follow_redirects=False)
        assert reject_alias.status_code == 303


def test_review_retries_reach_blocked_state(tmp_path: Path, monkeypatch) -> None:
    provider = FakeProvider()
    provider.review_failures_remaining = 3
    client = build_client(tmp_path, monkeypatch, provider=provider)
    headers = {"x-api-token": "test-token"}

    with client:
        response = client.post(
            "/api/tasks",
            headers=headers,
            json={
                "title": "Reviewer retry path",
                "description": "Exercise the reviewer rejection loop until the run blocks.",
                "workspace_path": "/tmp/repo",
                "constraints": ["Do not ship unresolved review items."],
                "target_files": ["app/services/orchestration_service.py"],
                "provider": "lmstudio",
                "model": "review-model",
            },
        )
        assert response.status_code == 200
        run_id = response.json()["run_id"]

        assert (
            wait_for_run_status(client, run_id, headers, {"blocked", "awaiting_approval"})
            == "blocked"
        )

        history = client.get(f"/api/runs/{run_id}/history", headers=headers)
        assert history.status_code == 200
        event_types = [item["event_type"] for item in history.json()]
        assert event_types.count("review_rejected") == 3
        assert "run_blocked" in event_types

        run_summary = client.get(f"/api/runs/{run_id}", headers=headers)
        assert run_summary.status_code == 200
        assert run_summary.json()["task"]["workspace_path"] == "/tmp/repo"
        assert run_summary.json()["task"]["provider_override"] == "lmstudio"
        assert run_summary.json()["task"]["model_override"] == "review-model"


def test_validation_retries_reach_blocked_state(tmp_path: Path, monkeypatch) -> None:
    provider = FakeProvider()
    provider.test_failures_remaining = 3
    client = build_client(tmp_path, monkeypatch, provider=provider)
    headers = {"x-api-token": "test-token"}

    with client:
        response = client.post(
            "/api/tasks",
            headers=headers,
            json={
                "title": "Validation retry path",
                "description": "Exercise the validation retry loop until the run blocks.",
                "task_type": "bugfix",
            },
        )
        assert response.status_code == 200
        run_id = response.json()["run_id"]

        assert (
            wait_for_run_status(client, run_id, headers, {"blocked", "awaiting_approval"})
            == "blocked"
        )

        history = client.get(f"/api/runs/{run_id}/history", headers=headers)
        assert history.status_code == 200
        event_types = [item["event_type"] for item in history.json()]
        assert event_types.count("tests_failed") == 3
        assert "run_blocked" in event_types

        snapshots = client.get(f"/api/runs/{run_id}/state-snapshots", headers=headers)
        assert snapshots.status_code == 200
        assert any(item["status"] == "blocked" for item in snapshots.json())


def test_planner_timeout_retries_then_fails(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("PLANNER_STAGE_TIMEOUT_SECONDS", "0.05")
    monkeypatch.setenv("PLANNER_STAGE_MAX_RETRIES", "1")
    provider = SlowPlannerProvider()
    client = build_client(tmp_path, monkeypatch, provider=provider)
    headers = {"x-api-token": "test-token"}

    with client:
        response = client.post(
            "/api/tasks",
            headers=headers,
            json={
                "title": "Planner timeout guard",
                "request_text": "Exercise planner timeout guard behavior.",
            },
        )
        assert response.status_code == 200
        run_id = response.json()["run_id"]

        assert (
            wait_for_run_status(client, run_id, headers, {"failed", "awaiting_approval"})
            == "failed"
        )

        history = client.get(f"/api/runs/{run_id}/history", headers=headers)
        assert history.status_code == 200
        event_types = [item["event_type"] for item in history.json()]
        assert event_types.count("planner_timeout") >= 1
        assert "planner_retry" in event_types
        assert "planner_failed" in event_types
