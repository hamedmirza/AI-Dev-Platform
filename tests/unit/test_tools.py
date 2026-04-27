import pytest

from app.core.exceptions import ConfigurationError
from app.schemas.task import TaskCreate
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
