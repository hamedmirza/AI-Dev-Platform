import json
import time
from pathlib import Path

from fastapi.testclient import TestClient

from app.core.enums import ProviderStatus
from app.core.settings import clear_settings_cache
from app.providers.base import BaseProvider
from app.providers.registry import set_provider_override
from app.schemas.provider import ProviderHealthResponse
from app.services.orchestration_service import reset_orchestration_service


class FakeProvider(BaseProvider):
    def invoke_json(self, system_prompt: str, user_prompt: str) -> str:
        prompt = f"{system_prompt}\n{user_prompt}".lower()
        if "summary, assumptions, risks, steps" in prompt:
            payload = {
                "summary": "Implement the requested backend feature.",
                "assumptions": ["Repository is configured."],
                "risks": ["External provider may fail."],
                "steps": ["Inspect current code", "Propose changes", "Validate outputs"],
                "acceptance_criteria": ["Routes respond", "Artifacts are stored"],
            }
        elif "touched_modules" in prompt:
            payload = {
                "touched_modules": ["app/api", "app/services"],
                "file_change_plan": ["Add API endpoints", "Store artifacts"],
                "dependency_notes": [],
                "migration_notes": [],
            }
        elif "changed_files" in prompt:
            payload = {
                "changed_files": ["app/api/main.py", "app/services/orchestration_service.py"],
                "implementation_notes": ["Create a runnable backend skeleton."],
                "requires_operator_approval": True,
            }
        elif "approved" in prompt:
            payload = {
                "approved": True,
                "summary": "Change set is acceptable.",
                "issues": [],
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


def build_client(tmp_path: Path, monkeypatch) -> TestClient:
    db_path = tmp_path / "test.db"
    workspace_root = tmp_path / "workspace"
    backup_root = tmp_path / "backups"
    monkeypatch.setenv("DB_URL", f"sqlite:///{db_path}")
    monkeypatch.setenv("APP_API_TOKEN", "test-token")
    monkeypatch.setenv("WORKSPACE_ROOT", str(workspace_root))
    monkeypatch.setenv("BACKUP_ROOT", str(backup_root))

    clear_settings_cache()
    reset_orchestration_service()
    set_provider_override(FakeProvider())

    from app.api.main import create_app

    return TestClient(create_app())


def test_health_endpoint(tmp_path: Path, monkeypatch) -> None:
    client = build_client(tmp_path, monkeypatch)
    with client:
        response = client.get("/api/health")
        assert response.status_code == 200
        assert response.json() == {"status": "ok"}

        provider = client.get("/api/health/provider")
        assert provider.status_code == 200
        assert provider.json()["status"] == "healthy"


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

        run_id = created["run_id"]
        for _ in range(40):
            run_response = client.get(f"/api/runs/{run_id}", headers=headers)
            assert run_response.status_code == 200
            status = run_response.json()["status"]
            if status in {"awaiting_approval", "failed", "needs_revision"}:
                break
            time.sleep(0.05)

        assert status == "awaiting_approval"

        history = client.get(f"/api/runs/{run_id}/history", headers=headers)
        assert history.status_code == 200
        assert any(item["event_type"] == "awaiting_approval" for item in history.json())

        artifacts = client.get(f"/api/runs/{run_id}/artifacts", headers=headers)
        assert artifacts.status_code == 200
        artifact_types = {item["artifact_type"] for item in artifacts.json()}
        assert artifact_types == {"plan", "architecture", "code_change", "review", "test_result"}


def test_config_requires_authentication(tmp_path: Path, monkeypatch) -> None:
    client = build_client(tmp_path, monkeypatch)
    with client:
        response = client.get("/api/config")
        assert response.status_code == 401
