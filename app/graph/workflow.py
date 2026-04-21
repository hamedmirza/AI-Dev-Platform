
from app.core.enums import RunStage, RunStatus
from app.graph.edges import next_stage
from app.graph.state import WorkflowState


def build_initial_state(run_id: str, task_id: str) -> WorkflowState:
    return {
        "run_id": run_id,
        "task_id": task_id,
        "stage": RunStage.INTAKE,
        "status": RunStatus.PENDING,
    }


def advance_state(state: WorkflowState, status: str | None = None) -> WorkflowState:
    current_status = status or state.get("status", RunStatus.RUNNING)
    state["status"] = current_status
    state["stage"] = next_stage(state.get("stage", RunStage.INTAKE), current_status)
    return state
