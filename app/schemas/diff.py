from pydantic import BaseModel


class DiffResponse(BaseModel):
    workspace_path: str
    branch: str = ""
    has_changes: bool
    changed_files: list[str]
    diff_text: str
