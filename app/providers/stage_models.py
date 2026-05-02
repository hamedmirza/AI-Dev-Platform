"""Resolve effective LM Studio model id for a pipeline stage."""

from __future__ import annotations

import json
from typing import Optional

from app.core.enums import RunStage
from app.core.settings import Settings
from app.db.models import TaskModel

_STAGE_ATTR: dict[RunStage, str] = {
    RunStage.PLANNER: "lmstudio_model_planner",
    RunStage.ARCHITECT: "lmstudio_model_architect",
    RunStage.UI_DESIGNER: "lmstudio_model_ui_designer",
    RunStage.CODER: "lmstudio_model_coder",
    RunStage.REVIEWER: "lmstudio_model_reviewer",
    RunStage.TESTER: "lmstudio_model_tester",
}


def effective_lmstudio_model_for_stage(
    task: TaskModel,
    stage: RunStage,
    settings: Settings,
) -> Optional[str]:
    """Return explicit model name or None so resolve_provider falls back to the default."""
    raw = (task.stage_models_json or "").strip()
    if raw:
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            data = {}
        if isinstance(data, dict):
            v = data.get(stage.value) or data.get(stage.value.upper())
            if isinstance(v, str) and v.strip():
                return v.strip()

    attr = _STAGE_ATTR.get(stage)
    if attr:
        val = getattr(settings, attr, None)
        if isinstance(val, str) and val.strip():
            return val.strip()

    if task.model_override and str(task.model_override).strip():
        return str(task.model_override).strip()

    return None
