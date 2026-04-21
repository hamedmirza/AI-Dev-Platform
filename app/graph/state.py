
from typing import TypedDict


class WorkflowState(TypedDict, total=False):
    run_id: str
    task_id: str
    stage: str
    status: str
    error_message: str
