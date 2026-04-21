
from app.services.repository_service import get_run_workspace_diff


def summarize_run_diff(run_id: str) -> dict[str, object]:
    diff = get_run_workspace_diff(run_id)
    diff_text = str(diff["diff_text"])
    return {
        "run_id": run_id,
        "has_changes": diff["has_changes"],
        "changed_files": diff["changed_files"],
        "summary": diff_text[:2000] if diff_text else "",
    }
