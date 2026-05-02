"""
Forty automated scenarios against the real FastAPI application.

Each scenario states a *rationale* (why we exercise this path) and *facts*
(assertions on HTTP status codes, JSON bodies, DB-backed run state, and
artifact payloads). Runs use the same ``FakeProvider`` as ``tests/unit/test_api.py``,
so the LLM is deterministic and the suite stays fast without LM Studio.

Agent "task lists" here mean structured planner/architect outputs persisted as
artifacts: non-empty ``steps`` and ``acceptance_criteria`` on the plan artifact,
and ``file_change_plan`` on the architecture artifact — verified where noted.
"""

from __future__ import annotations

import json
import uuid
from collections.abc import Callable
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.db.models import RunModel, TaskModel
from app.db.session import get_session_factory
from tests.unit.test_api import (
    FakeProvider,
    MalformedCoderProvider,
    MalformedUIDesignerOnceProvider,
    ScopeViolationProvider,
    build_client,
    wait_for_run_status,
)

HDR = {"x-api-token": "test-token"}
REQ = "Minimum ten chars of request text describing a change for the operator."


def _assert_planner_task_list_facts(artifacts: list[dict]) -> None:
    """Planner output is persisted: steps and acceptance criteria must be present."""
    plans = [a for a in artifacts if a.get("artifact_type") == "plan"]
    assert len(plans) >= 1, "fact: at least one plan artifact exists"
    body = json.loads(plans[0]["content"])
    steps = body.get("steps")
    crit = body.get("acceptance_criteria")
    assert isinstance(steps, list) and len(steps) >= 1, (
        f"fact: planner steps non-empty, got {steps!r}"
    )
    assert isinstance(crit, list) and len(crit) >= 1, (
        f"fact: acceptance_criteria non-empty, got {crit!r}"
    )


def _assert_architect_plan_facts(artifacts: list[dict]) -> None:
    arch = [a for a in artifacts if a.get("artifact_type") == "architecture"]
    assert len(arch) >= 1, "fact: architecture artifact exists"
    body = json.loads(arch[0]["content"])
    fcp = body.get("file_change_plan")
    assert isinstance(fcp, list) and len(fcp) >= 1, f"fact: file_change_plan non-empty, got {fcp!r}"


def _assert_full_agent_artifact_set(artifacts: list[dict]) -> None:
    types = {a["artifact_type"] for a in artifacts}
    expected = {
        "plan",
        "architecture",
        "ui_design",
        "code_change",
        "review",
        "test_result",
        "log",
    }
    missing = expected - types
    assert not missing, f"fact: artifact types include pipeline outputs, missing={missing}"


def _create_run(client: TestClient, payload: dict) -> str:
    r = client.post("/api/tasks", headers=HDR, json=payload)
    assert r.status_code == 200, r.text
    return str(r.json()["run_id"])


def _artifacts(client: TestClient, run_id: str) -> list[dict]:
    r = client.get(f"/api/runs/{run_id}/artifacts", headers=HDR)
    assert r.status_code == 200
    return r.json()


# --- scenario handlers: (tmp_path, monkeypatch) -> None


def s01_health_live(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Rationale: load balancers rely on a cheap liveness JSON."""
    with build_client(tmp_path, monkeypatch) as c:
        r = c.get("/api/health/live")
        assert r.status_code == 200
        assert r.json() == {"status": "live"}


def s02_health(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Rationale: aggregate health reports ok for the API process."""
    with build_client(tmp_path, monkeypatch) as c:
        r = c.get("/api/health")
        assert r.status_code == 200
        assert r.json().get("status") == "ok"
        assert r.headers.get("x-request-id")


def s03_health_ready(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Rationale: readiness must include database connectivity."""
    with build_client(tmp_path, monkeypatch) as c:
        r = c.get("/api/health/ready")
        assert r.status_code == 200
        body = r.json()
        assert body.get("status") == "ready"
        assert body.get("database") == "ok"


def s04_health_provider(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Rationale: provider adapter must report healthy under fake provider."""
    with build_client(tmp_path, monkeypatch) as c:
        r = c.get("/api/health/provider")
        assert r.status_code == 200
        assert r.json().get("status") == "healthy"


def s05_health_repository(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Rationale: configured git source repo path is exposed for operators."""
    with build_client(tmp_path, monkeypatch) as c:
        r = c.get("/api/health/repository")
        assert r.status_code == 200
        assert "source-repo" in r.json().get("path", "")


def s06_health_github(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Rationale: GitHub integration status is explicit when unset."""
    with build_client(tmp_path, monkeypatch) as c:
        r = c.get("/api/health/github")
        assert r.status_code == 200
        assert r.json().get("configured") is False


def s07_config(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Rationale: authenticated operators read runtime config snapshot."""
    with build_client(tmp_path, monkeypatch) as c:
        r = c.get("/api/config", headers=HDR)
        assert r.status_code == 200
        assert "runtime" in r.json()
        assert r.json()["runtime"].get("app_port") == 8400


def s08_runs_list(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Rationale: runs listing returns a JSON array (possibly empty)."""
    with build_client(tmp_path, monkeypatch) as c:
        r = c.get("/api/runs?limit=5", headers=HDR)
        assert r.status_code == 200
        assert isinstance(r.json(), list)


def s09_backups_list(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Rationale: backup index is readable before any backup exists."""
    with build_client(tmp_path, monkeypatch) as c:
        r = c.get("/api/backups", headers=HDR)
        assert r.status_code == 200
        assert isinstance(r.json(), list)


def s10_lmstudio_models(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Rationale: LM Studio model discovery endpoint returns structured result."""
    with build_client(tmp_path, monkeypatch) as c:
        r = c.get("/api/config/lmstudio/models", headers=HDR)
        assert r.status_code == 200
        body = r.json()
        assert "models" in body and isinstance(body["models"], list)


def s11_tasks_unauthorized(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Rationale: task creation requires API token or operator cookie."""
    with build_client(tmp_path, monkeypatch) as c:
        r = c.post("/api/tasks", json={"title": "abc", "request_text": REQ})
        assert r.status_code == 401


def s12_run_not_found(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Rationale: unknown run ids are 404, not 500."""
    with build_client(tmp_path, monkeypatch) as c:
        rid = str(uuid.uuid4())
        r = c.get(f"/api/runs/{rid}", headers=HDR)
        assert r.status_code == 404


def s13_title_too_short(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Rationale: Pydantic enforces title min length."""
    with build_client(tmp_path, monkeypatch) as c:
        r = c.post("/api/tasks", headers=HDR, json={"title": "ab", "request_text": REQ})
        assert r.status_code == 422


def s14_missing_request_and_description(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Rationale: model requires description or request_text."""
    with build_client(tmp_path, monkeypatch) as c:
        r = c.post("/api/tasks", headers=HDR, json={"title": "Valid title"})
        assert r.status_code == 422


def s15_bad_stage_models_key(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Rationale: unknown stage keys in stage_models are rejected."""
    with build_client(tmp_path, monkeypatch) as c:
        r = c.post(
            "/api/tasks",
            headers=HDR,
            json={"title": "Title ok", "request_text": REQ, "stage_models": {"unknown": "m"}},
        )
        assert r.status_code == 422


def s16_title_max_length_ok(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Rationale: boundary — 255-char title is accepted."""
    title = "T" * 255
    with build_client(tmp_path, monkeypatch) as c:
        run_id = _create_run(c, {"title": title, "request_text": REQ})
        assert wait_for_run_status(c, run_id, HDR, {"awaiting_approval", "failed", "blocked"}) == (
            "awaiting_approval"
        )


def s17_description_only(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Rationale: description alone satisfies request text derivation."""
    with build_client(tmp_path, monkeypatch) as c:
        run_id = _create_run(
            c,
            {
                "title": "Desc only task",
                "description": "Ten plus chars description for the task body here.",
            },
        )
        assert wait_for_run_status(c, run_id, HDR, {"awaiting_approval", "failed", "blocked"}) == (
            "awaiting_approval"
        )


def s18_source_repo_disallowed_remote(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Rationale: remote URLs require ALLOWED_GIT_HOSTS configuration."""
    with build_client(tmp_path, monkeypatch) as c:
        r = c.post(
            "/api/tasks",
            headers=HDR,
            json={
                "title": "Remote src",
                "request_text": REQ,
                "source_repo": "https://github.com/foo/bar.git",
            },
        )
        assert r.status_code == 422


def s19_constraints_and_targets(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Rationale: constraints and target_files are stored and runs still complete."""
    with build_client(tmp_path, monkeypatch) as c:
        run_id = _create_run(
            c,
            {
                "title": "Scoped constraints run",
                "request_text": REQ,
                "constraints": ["keep-diff-small", "no-new-deps"],
                "target_files": ["README.md"],
            },
        )
        assert wait_for_run_status(c, run_id, HDR, {"awaiting_approval", "failed", "blocked"}) == (
            "awaiting_approval"
        )
        summary = c.get(f"/api/runs/{run_id}", headers=HDR).json()
        assert "keep-diff-small" in summary["task"]["constraints"]
        assert "README.md" in summary["task"]["target_files"]


def s20_task_type_and_models(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Rationale: task_type and per-stage model map are accepted."""
    with build_client(tmp_path, monkeypatch) as c:
        run_id = _create_run(
            c,
            {
                "title": "Typed task with models",
                "request_text": REQ,
                "task_type": "feature",
                "stage_models": {"coder": "fake-coder", "planner": "fake-planner"},
            },
        )
        assert wait_for_run_status(c, run_id, HDR, {"awaiting_approval", "failed", "blocked"}) == (
            "awaiting_approval"
        )


def s21_planner_steps_verified(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Rationale: planner artifact contains deployable step list (fact)."""
    with build_client(tmp_path, monkeypatch) as c:
        run_id = _create_run(c, {"title": "Verify planner artifact", "request_text": REQ})
        assert wait_for_run_status(c, run_id, HDR, {"awaiting_approval", "failed", "blocked"}) == (
            "awaiting_approval"
        )
        _assert_planner_task_list_facts(_artifacts(c, run_id))


def s22_architect_plan_verified(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Rationale: architect persists file_change_plan (fact)."""
    with build_client(tmp_path, monkeypatch) as c:
        run_id = _create_run(c, {"title": "Verify architect artifact", "request_text": REQ})
        assert wait_for_run_status(c, run_id, HDR, {"awaiting_approval", "failed", "blocked"}) == (
            "awaiting_approval"
        )
        _assert_architect_plan_facts(_artifacts(c, run_id))


def s23_full_artifact_pipeline(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Rationale: all stage artifact types are recorded before approval."""
    with build_client(tmp_path, monkeypatch) as c:
        run_id = _create_run(c, {"title": "Full artifact coverage", "request_text": REQ})
        assert wait_for_run_status(c, run_id, HDR, {"awaiting_approval", "failed", "blocked"}) == (
            "awaiting_approval"
        )
        _assert_full_agent_artifact_set(_artifacts(c, run_id))


def s24_use_scout(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Rationale: use_scout is persisted on the task row for orchestration (DB fact)."""
    with build_client(tmp_path, monkeypatch) as c:
        run_id = _create_run(
            c,
            {"title": "Scout preamble run", "request_text": REQ, "use_scout": True},
        )
        assert wait_for_run_status(c, run_id, HDR, {"awaiting_approval", "failed", "blocked"}) == (
            "awaiting_approval"
        )
        session = get_session_factory()()
        try:
            run = session.get(RunModel, run_id)
            assert run is not None
            task = session.get(TaskModel, run.task_id)
            assert task is not None
            assert task.use_scout is True, "fact: task.use_scout stored True when requested"
        finally:
            session.close()


def s25_snapshots_include_stages(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Rationale: state snapshots record stage progression."""
    with build_client(tmp_path, monkeypatch) as c:
        run_id = _create_run(c, {"title": "Snapshot stages", "request_text": REQ})
        assert wait_for_run_status(c, run_id, HDR, {"awaiting_approval", "failed", "blocked"}) == (
            "awaiting_approval"
        )
        snaps = c.get(f"/api/runs/{run_id}/state-snapshots", headers=HDR).json()
        stages = {s["stage"] for s in snaps}
        assert "planner" in stages and "tester" in stages, f"fact: stages seen: {stages}"


def s26_workspace_patch_applied(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Rationale: coder patch lands on workspace README (file fact)."""
    with build_client(tmp_path, monkeypatch) as c:
        run_id = _create_run(c, {"title": "Workspace patch", "request_text": REQ})
        assert wait_for_run_status(c, run_id, HDR, {"awaiting_approval", "failed", "blocked"}) == (
            "awaiting_approval"
        )
        readme = tmp_path / "workspace" / f"run-{run_id}" / "README.md"
        text = readme.read_text(encoding="utf-8")
        assert "updated by ai" in text, f"fact: expected coder patch phrase in README, got {text!r}"


def s27_history_terminal_events(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Rationale: operator-visible timeline includes patch and validation markers."""
    with build_client(tmp_path, monkeypatch) as c:
        run_id = _create_run(c, {"title": "History markers", "request_text": REQ})
        assert wait_for_run_status(c, run_id, HDR, {"awaiting_approval", "failed", "blocked"}) == (
            "awaiting_approval"
        )
        ev = [e["event_type"] for e in c.get(f"/api/runs/{run_id}/history", headers=HDR).json()]
        assert "code_patch_applied" in ev
        assert "validation_commands_completed" in ev
        assert "awaiting_approval" in ev


def s28_diff_endpoint(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Rationale: diff API reflects workspace branch state."""
    with build_client(tmp_path, monkeypatch) as c:
        run_id = _create_run(c, {"title": "Diff check", "request_text": REQ})
        assert wait_for_run_status(c, run_id, HDR, {"awaiting_approval", "failed", "blocked"}) == (
            "awaiting_approval"
        )
        d = c.get(f"/api/runs/{run_id}/diff", headers=HDR).json()
        assert d.get("branch") == f"run/{run_id}"
        assert "README.md" in d.get("changed_files", [])


def s29_workspace_file_io(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Rationale: operator can read/write workspace file via API."""
    with build_client(tmp_path, monkeypatch) as c:
        run_id = _create_run(c, {"title": "File IO", "request_text": REQ})
        assert wait_for_run_status(c, run_id, HDR, {"awaiting_approval", "failed", "blocked"}) == (
            "awaiting_approval"
        )
        w = c.post(
            f"/api/runs/{run_id}/workspace/file",
            headers=HDR,
            json={"path": "README.md", "content": "fixture repo\npatched-by-test\n"},
        )
        assert w.status_code == 200
        rb = c.get(
            f"/api/runs/{run_id}/workspace/file",
            headers=HDR,
            params={"path": "README.md"},
        )
        assert rb.status_code == 200
        assert "patched-by-test" in rb.json()["content"]


def s30_ui_design_artifact_json(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Rationale: UI designer JSON includes layout_plan list."""
    with build_client(tmp_path, monkeypatch) as c:
        run_id = _create_run(c, {"title": "UI artifact shape", "request_text": REQ})
        assert wait_for_run_status(c, run_id, HDR, {"awaiting_approval", "failed", "blocked"}) == (
            "awaiting_approval"
        )
        arts = _artifacts(c, run_id)
        ui = next(a for a in arts if a["artifact_type"] == "ui_design")
        body = json.loads(ui["content"])
        assert isinstance(body.get("layout_plan"), list) and len(body["layout_plan"]) >= 1


def s31_approve_completes(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Rationale: approve transitions to completed and done stage."""
    with build_client(tmp_path, monkeypatch) as c:
        run_id = _create_run(c, {"title": "Approve path", "request_text": REQ})
        assert wait_for_run_status(c, run_id, HDR, {"awaiting_approval", "failed", "blocked"}) == (
            "awaiting_approval"
        )
        (tmp_path / "workspace" / f"run-{run_id}" / "README.md").write_text(
            "fixture repo\nclean\n", encoding="utf-8"
        )
        ap = c.post(f"/api/runs/{run_id}/approve", headers=HDR, json={"note": "ok"})
        assert ap.status_code == 200
        assert ap.json()["status"] == "completed"
        fin = c.get(f"/api/runs/{run_id}", headers=HDR).json()
        assert fin["latest_state"]["stage"] == "done"


def s32_reject_review_required(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Rationale: reject returns run to review_required for another coder cycle."""
    with build_client(tmp_path, monkeypatch) as c:
        run_id = _create_run(c, {"title": "Reject path", "request_text": REQ})
        assert wait_for_run_status(c, run_id, HDR, {"awaiting_approval", "failed", "blocked"}) == (
            "awaiting_approval"
        )
        rj = c.post(f"/api/runs/{run_id}/reject", headers=HDR, json={"note": "no"})
        assert rj.status_code == 200
        body = c.get(f"/api/runs/{run_id}", headers=HDR).json()
        assert body["status"] == "review_required"
        assert body["current_stage"] == "coder"


def s33_abort_from_awaiting(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Rationale: operator can cancel a run waiting for approval."""
    with build_client(tmp_path, monkeypatch) as c:
        run_id = _create_run(c, {"title": "Abort path", "request_text": REQ})
        assert wait_for_run_status(c, run_id, HDR, {"awaiting_approval", "failed", "blocked"}) == (
            "awaiting_approval"
        )
        ab = c.post(f"/api/runs/{run_id}/abort", headers=HDR, json={"note": "stop"})
        assert ab.status_code == 200
        assert c.get(f"/api/runs/{run_id}", headers=HDR).json()["status"] == "cancelled"


def s34_malformed_coder_blocked(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Rationale: invalid coder JSON exhausts retries and blocks."""
    with build_client(tmp_path, monkeypatch, provider=MalformedCoderProvider()) as c:
        run_id = _create_run(c, {"title": "Bad coder", "request_text": REQ})
        assert wait_for_run_status(c, run_id, HDR, {"blocked"}) == "blocked"
        err = c.get(f"/api/runs/{run_id}", headers=HDR).json().get("error_message") or ""
        assert "Coder" in err


def s35_scope_guard_blocked(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Rationale: patches outside target_files are rejected."""
    with build_client(tmp_path, monkeypatch, provider=ScopeViolationProvider()) as c:
        run_id = _create_run(
            c,
            {
                "title": "Scope guard",
                "request_text": REQ,
                "target_files": ["app/ui/render.py"],
            },
        )
        assert wait_for_run_status(c, run_id, HDR, {"blocked"}) == "blocked"


def s36_malformed_ui_recovers(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Rationale: one bad UI JSON retry still reaches approval."""
    with build_client(tmp_path, monkeypatch, provider=MalformedUIDesignerOnceProvider()) as c:
        run_id = _create_run(c, {"title": "UI retry ok", "request_text": REQ})
        assert wait_for_run_status(c, run_id, HDR, {"awaiting_approval"}) == "awaiting_approval"
        ev = [e["event_type"] for e in c.get(f"/api/runs/{run_id}/history", headers=HDR).json()]
        assert "ui_designer_retry" in ev


def s37_review_blocked(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Rationale: persistent reviewer rejection blocks the run."""
    provider = FakeProvider()
    provider.review_failures_remaining = 3
    with build_client(tmp_path, monkeypatch, provider=provider) as c:
        run_id = _create_run(
            c,
            {
                "title": "Review block",
                "description": "Exercise reviewer rejection loop until blocked.",
                "workspace_path": "/tmp/repo",
                "constraints": ["strict review"],
                "provider": "lmstudio",
                "model": "m",
            },
        )
        assert wait_for_run_status(c, run_id, HDR, {"blocked", "awaiting_approval"}) == "blocked"
        ev = [e["event_type"] for e in c.get(f"/api/runs/{run_id}/history", headers=HDR).json()]
        assert ev.count("review_rejected") == 3


def s38_retry_resets_pending(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Rationale: retry clears error and requeues."""
    with build_client(tmp_path, monkeypatch) as c:
        run_id = _create_run(c, {"title": "Retry reset", "request_text": REQ})
        assert wait_for_run_status(c, run_id, HDR, {"awaiting_approval", "failed", "blocked"}) == (
            "awaiting_approval"
        )
        c.post(f"/api/runs/{run_id}/reject", headers=HDR, json={"note": "r"})
        rt = c.post(f"/api/runs/{run_id}/retry", headers=HDR, json={"note": "go"})
        assert rt.status_code == 200
        assert rt.json()["status"] == "pending"


def s39_cleanup_workspace(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Rationale: cleanup removes workspace folder after terminal-ish state."""
    with build_client(tmp_path, monkeypatch) as c:
        run_id = _create_run(c, {"title": "Cleanup", "request_text": REQ})
        assert wait_for_run_status(c, run_id, HDR, {"awaiting_approval", "failed", "blocked"}) == (
            "awaiting_approval"
        )
        c.post(f"/api/runs/{run_id}/abort", headers=HDR, json={"note": "x"})
        cl = c.post(f"/api/runs/{run_id}/cleanup-workspace", headers=HDR)
        assert cl.status_code == 200
        assert cl.json().get("removed") is True


def s40_ui_shell_login(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Rationale: login page is public HTML; dashboard shell requires cookie then embeds React."""
    with build_client(tmp_path, monkeypatch) as c:
        p = c.get("/ui/login")
        assert p.status_code == 200
        assert "Operator Login" in p.text
        redir = c.post("/ui/login", data={"token": "test-token"}, follow_redirects=False)
        assert redir.status_code == 303
        dash = c.get("/ui")
        assert dash.status_code == 200
        assert "root" in dash.text and "/ui/assets/" in dash.text


SCENARIOS: list[tuple[str, str, Callable[[Path, pytest.MonkeyPatch], None]]] = [
    ("S01_health_live", "Expose liveness JSON for probes.", s01_health_live),
    ("S02_health", "Aggregate API health with request id.", s02_health),
    ("S03_health_ready", "Readiness includes database ok.", s03_health_ready),
    ("S04_health_provider", "Provider health is healthy under fake LLM.", s04_health_provider),
    (
        "S05_health_repository",
        "Repository health points at fixture clone path.",
        s05_health_repository,
    ),
    ("S06_health_github", "GitHub configured flag is false without token.", s06_health_github),
    ("S07_config", "Config route returns runtime map when authed.", s07_config),
    ("S08_runs_list", "Runs list endpoint returns JSON array.", s08_runs_list),
    ("S09_backups_list", "Backups list is readable.", s09_backups_list),
    ("S10_lmstudio_models", "LM Studio models endpoint returns models key.", s10_lmstudio_models),
    ("S11_tasks_unauthorized", "Task POST without token is 401.", s11_tasks_unauthorized),
    ("S12_run_not_found", "Unknown run GET is 404.", s12_run_not_found),
    ("S13_title_too_short", "Short title rejected with 422.", s13_title_too_short),
    ("S14_missing_request", "Missing body fields yield 422.", s14_missing_request_and_description),
    ("S15_bad_stage_models", "Invalid stage_models keys yield 422.", s15_bad_stage_models_key),
    ("S16_title_max", "255-char title still runs to approval gate.", s16_title_max_length_ok),
    ("S17_description_only", "Description-only task completes pipeline.", s17_description_only),
    (
        "S18_source_repo_disallowed",
        "Remote source without allowlist is 422.",
        s18_source_repo_disallowed_remote,
    ),
    (
        "S19_constraints_targets",
        "Constraints and targets persist on task.",
        s19_constraints_and_targets,
    ),
    ("S20_task_type_models", "task_type and stage_models accepted.", s20_task_type_and_models),
    ("S21_planner_steps", "Plan artifact contains non-empty steps.", s21_planner_steps_verified),
    (
        "S22_architect_plan",
        "Architecture artifact has file_change_plan.",
        s22_architect_plan_verified,
    ),
    ("S23_full_artifacts", "All pipeline artifact types present.", s23_full_artifact_pipeline),
    ("S24_use_scout", "use_scout persisted on task for orchestration.", s24_use_scout),
    ("S25_snapshots", "Snapshots include planner and tester stages.", s25_snapshots_include_stages),
    ("S26_workspace_patch", "README contains coder patch phrase.", s26_workspace_patch_applied),
    (
        "S27_history_events",
        "History lists patch, validation, approval wait.",
        s27_history_terminal_events,
    ),
    ("S28_diff", "Diff API names branch and changed README.", s28_diff_endpoint),
    ("S29_workspace_file_io", "Workspace file POST/GET round trip.", s29_workspace_file_io),
    (
        "S30_ui_design_json",
        "UI design artifact has layout_plan array.",
        s30_ui_design_artifact_json,
    ),
    ("S31_approve", "Approve completes run to done.", s31_approve_completes),
    ("S32_reject", "Reject sets review_required and coder stage.", s32_reject_review_required),
    ("S33_abort", "Abort cancels awaiting run.", s33_abort_from_awaiting),
    ("S34_malformed_coder", "Malformed coder JSON leads to blocked.", s34_malformed_coder_blocked),
    ("S35_scope_guard", "Out-of-scope files blocked.", s35_scope_guard_blocked),
    ("S36_malformed_ui", "UI designer retry then approval.", s36_malformed_ui_recovers),
    ("S37_review_blocked", "Three review rejects block.", s37_review_blocked),
    ("S38_retry", "Retry after reject returns pending.", s38_retry_resets_pending),
    ("S39_cleanup", "Cleanup removes workspace after abort.", s39_cleanup_workspace),
    ("S40_ui_shell", "Login page loads; authed dashboard embeds React assets.", s40_ui_shell_login),
]

assert len(SCENARIOS) == 40, "scenario matrix must contain exactly 40 rows"


@pytest.mark.parametrize(
    "scenario_id,rationale,handler",
    SCENARIOS,
    ids=[row[0] for row in SCENARIOS],
)
def test_matrix_scenario(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    scenario_id: str,
    rationale: str,
    handler: Callable[[Path, pytest.MonkeyPatch], None],
) -> None:
    """Each row is an independent scenario; id + rationale show in ``pytest -v`` output."""
    _ = rationale  # surfaced via param id and docstrings on handlers
    handler(tmp_path, monkeypatch)
