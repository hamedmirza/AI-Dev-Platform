
from app.core.enums import RunStage, RunStatus


def next_stage(current_stage: str, current_status: str) -> str:
    if current_status in {RunStatus.FAILED, RunStatus.CANCELLED, RunStatus.COMPLETED}:
        return RunStage.DONE

    order = [
        RunStage.INTAKE.value,
        RunStage.PLANNER.value,
        RunStage.ARCHITECT.value,
        RunStage.UI_DESIGNER.value,
        RunStage.CODER.value,
        RunStage.REVIEWER.value,
        RunStage.TESTER.value,
        RunStage.APPROVAL.value,
        RunStage.DONE.value,
    ]
    try:
        idx = order.index(current_stage)
    except ValueError:
        return RunStage.DONE
    return order[min(idx + 1, len(order) - 1)]
