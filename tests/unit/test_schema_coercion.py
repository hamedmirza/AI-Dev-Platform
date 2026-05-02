from app.schemas.architecture import ArchitectureResponse
from app.schemas.code_change import CodeChangeResponse
from app.schemas.plan import PlanResponse
from app.schemas.review import ReviewResponse
from app.schemas.test_result import TestResultResponse as StageTestResultResponse
from app.schemas.ui_design import UIDesignResponse


def test_architecture_response_coerces_mixed_shapes() -> None:
    payload = {
        "touched_modules": "app/ui",
        "file_change_plan": [
            {"path": "app/ui/routes.py", "reason": "Improve UX"},
            {"path": "app/ui/render.py", "reason": "Refine styling"},
        ],
        "dependency_notes": "No dependency changes",
        "migration_notes": None,
    }
    model = ArchitectureResponse.model_validate(payload)
    assert model.touched_modules == ["app/ui"]
    assert model.file_change_plan == [
        "app/ui/routes.py: Improve UX",
        "app/ui/render.py: Refine styling",
    ]
    assert model.dependency_notes == ["No dependency changes"]
    assert model.migration_notes == []


def test_other_stage_models_coerce_lists_and_bools() -> None:
    plan = PlanResponse.model_validate(
        {
            "summary": "Plan",
            "assumptions": "Repo exists",
            "risks": None,
            "steps": ["one", {"path": "two", "reason": "detail"}],
            "acceptance_criteria": "done",
        }
    )
    assert plan.assumptions == ["Repo exists"]
    assert plan.risks == []
    assert plan.steps == ["one", "two: detail"]
    assert plan.acceptance_criteria == ["done"]

    code = CodeChangeResponse.model_validate(
        {
            "changed_files": {"path": "README.md", "reason": "note"},
            "implementation_notes": "small tweak",
            "requires_operator_approval": "yes",
            "line_changes": [
                {
                    "path": "README.md",
                    "operation": "insert_after",
                    "anchor": "## Frontend Build",
                    "content": "Built assets are served by FastAPI.",
                    "occurrence": 1,
                }
            ],
            "file_changes": [
                {
                    "path": "README.md",
                    "content": "updated\n",
                    "change_type": "upsert",
                }
            ],
        }
    )
    assert code.changed_files == ["README.md: note"]
    assert code.implementation_notes == ["small tweak"]
    assert code.requires_operator_approval is True
    assert code.line_changes[0].operation == "insert_after"
    assert code.file_changes[0].path == "README.md"

    review = ReviewResponse.model_validate(
        {"approved": "false", "summary": "Needs edits", "issues": "schema mismatch"}
    )
    assert review.approved is False
    assert review.issues == ["schema mismatch"]

    test_result = StageTestResultResponse.model_validate(
        {
            "passed": "1",
            "summary": "ok",
            "commands": "pytest -q",
            "failures": None,
        }
    )
    assert test_result.passed is True
    assert test_result.commands == ["pytest -q"]
    assert test_result.failures == []

    ui_design = UIDesignResponse.model_validate(
        {
            "design_summary": "Modern operations console",
            "visual_system": "Crisp surfaces",
            "layout_plan": [{"path": "app/ui/routes.py", "reason": "Rework dashboard"}],
            "interaction_notes": None,
            "accessibility_notes": "Keyboard focus states",
            "implementation_notes": "Use compact responsive grids",
        }
    )
    assert ui_design.visual_system == ["Crisp surfaces"]
    assert ui_design.layout_plan == ["app/ui/routes.py: Rework dashboard"]
    assert ui_design.interaction_notes == []
