"""Tests for advisory-field defaults in agent response schemas.

After M1 surfaced a real LLM (qwen3-coder-next) omitting the empty ``risks`` list from a
planner response — which is a perfectly reasonable thing for a model to do on a trivial
task — every agent response schema now defaults its advisory ``list[str]`` fields to ``[]``.
Structural fields (``summary``, ``steps``, ``acceptance_criteria``, ``file_change_plan``,
``layout_plan``, ``changed_files``) remain required so we still fail loudly when an LLM
omits something it must produce.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.schemas.architecture import ArchitectureResponse
from app.schemas.code_change import CodeChangeResponse
from app.schemas.plan import PlanResponse
from app.schemas.review import ReviewResponse
from app.schemas.test_result import TestResultResponse
from app.schemas.ui_design import UIDesignResponse


def test_plan_response_advisory_fields_default_empty() -> None:
    plan = PlanResponse.model_validate(
        {"summary": "small change", "steps": ["x"], "acceptance_criteria": ["y"]}
    )
    assert plan.assumptions == []
    assert plan.risks == []


def test_plan_response_structural_fields_still_required() -> None:
    with pytest.raises(ValidationError) as exc:
        PlanResponse.model_validate({"summary": "x", "acceptance_criteria": ["y"]})
    assert "steps" in str(exc.value)
    with pytest.raises(ValidationError) as exc:
        PlanResponse.model_validate({"summary": "x", "steps": ["a"]})
    assert "acceptance_criteria" in str(exc.value)


def test_architecture_response_advisory_fields_default_empty() -> None:
    arch = ArchitectureResponse.model_validate({"file_change_plan": ["edit README"]})
    assert arch.touched_modules == []
    assert arch.dependency_notes == []
    assert arch.migration_notes == []


def test_architecture_response_structural_field_required() -> None:
    with pytest.raises(ValidationError) as exc:
        ArchitectureResponse.model_validate({})
    assert "file_change_plan" in str(exc.value)


def test_ui_design_response_advisory_fields_default_empty() -> None:
    ui = UIDesignResponse.model_validate(
        {"design_summary": "no UI for this task", "layout_plan": ["unchanged"]}
    )
    assert ui.visual_system == []
    assert ui.interaction_notes == []
    assert ui.accessibility_notes == []
    assert ui.implementation_notes == []


def test_review_response_issues_default_empty() -> None:
    review = ReviewResponse.model_validate({"approved": True, "summary": "looks good"})
    assert review.issues == []


def test_test_result_response_lists_default_empty() -> None:
    result = TestResultResponse.model_validate({"passed": True, "summary": "skipped"})
    assert result.commands == []
    assert result.failures == []


def test_code_change_response_implementation_notes_default_empty() -> None:
    code = CodeChangeResponse.model_validate(
        {"changed_files": ["README.md"]}
    )
    assert code.implementation_notes == []
    assert code.line_changes == []
    assert code.file_changes == []


def test_code_change_response_changed_files_still_required() -> None:
    with pytest.raises(ValidationError) as exc:
        CodeChangeResponse.model_validate({})
    assert "changed_files" in str(exc.value)
