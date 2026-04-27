
from typing import TypedDict


class WorkflowState(TypedDict, total=False):
    run_id: str
    task_id: str
    title: str
    description: str
    workspace_path: str
    task_type: str
    constraints: list[str]
    target_files: list[str]
    stage: str
    status: str
    current_step: str
    planner_output: str
    architecture_output: str
    code_output: str
    review_output: str
    test_output: str
    artifacts: list[str]
    errors: list[str]
    retry_count: int
    error_message: str
