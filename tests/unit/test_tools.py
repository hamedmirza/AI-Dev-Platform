import pytest

from app.core.exceptions import ConfigurationError
from app.schemas.architecture import ArchitectureResponse
from app.schemas.plan import PlanResponse
from app.schemas.task import TaskCreate
from app.schemas.ui_design import UIDesignResponse
from app.services.orchestration_service import OrchestrationService
from app.tools.command_runner import run_validation_command


def test_task_create_accepts_spec_fields() -> None:
    payload = TaskCreate(
        title="Spec-compatible task",
        description="Implement the missing run lifecycle behavior.",
        workspace_path="/tmp/example",
        task_type="feature",
        constraints=["Keep changes scoped."],
        target_files=["app/services/orchestration_service.py"],
        provider="lmstudio",
        model="qwen",
    )

    prompt_text = payload.to_prompt_text()

    assert "Workspace path: /tmp/example" in prompt_text
    assert "Target files:" in prompt_text
    assert "- app/services/orchestration_service.py" in prompt_text


def test_validation_command_whitelist_blocks_unsafe_commands() -> None:
    with pytest.raises(ConfigurationError):
        run_validation_command(["bash", "-lc", "echo unsafe"])
    with pytest.raises(ConfigurationError):
        run_validation_command(["pytest"])
    with pytest.raises(ConfigurationError):
        run_validation_command(["mypy", "app", "--install-types"])


def test_coder_and_tester_prompts_include_safety_constraints() -> None:
    coder_prompt = open("app/agents/prompts/coder.md", encoding="utf-8").read()
    tester_prompt = open("app/agents/prompts/tester.md", encoding="utf-8").read()

    assert "APIRouter" in coder_prompt
    assert "Do not replace `app/ui/routes.py` with a standalone `FastAPI()` app." in coder_prompt
    assert "login, dashboard, repository, provider, settings, backups" in coder_prompt
    assert "ruff check ." in tester_prompt
    assert "mypy app" in tester_prompt
    assert "pytest -q" in tester_prompt
    assert "Do not emit shell builtins" in tester_prompt
    assert "grep" in tester_prompt


def test_orchestration_requests_reinforce_ui_and_validation_constraints() -> None:
    service = OrchestrationService()
    coder_request = service._build_coder_request(
        "Improve the UI.",
        "missing-run",
        [],
        PlanResponse(
            summary="Plan",
            assumptions=[],
            risks=[],
            steps=[],
            acceptance_criteria=[],
        ),
        ArchitectureResponse(
            touched_modules=["app/ui"],
            file_change_plan=["Update render helpers"],
            dependency_notes=[],
            migration_notes=[],
        ),
        UIDesignResponse(
            design_summary="Modern UI",
            visual_system=[],
            layout_plan=[],
            interaction_notes=[],
            accessibility_notes=[],
            implementation_notes=[],
        ),
        retry_feedback=[],
    )
    test_request = service._build_test_request("Improve the UI.", retry_feedback=[])

    assert "Preserve existing FastAPI APIRouter setup" in coder_request
    assert "Do not create a standalone FastAPI() app" in coder_request
    assert "workspace editor" in coder_request
    assert "Validation command whitelist" in test_request
    assert "ruff check ." in test_request
    assert "python -c" in test_request
