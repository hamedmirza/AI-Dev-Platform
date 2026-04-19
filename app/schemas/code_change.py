
from pydantic import BaseModel


class CodeChangeResponse(BaseModel):
    changed_files: list[str]
    implementation_notes: list[str]
    requires_operator_approval: bool = True
