
from pydantic import BaseModel, field_validator

from app.schemas._coerce import as_bool, as_string_list


class CodeChangeResponse(BaseModel):
    changed_files: list[str]
    implementation_notes: list[str]
    requires_operator_approval: bool = True

    @field_validator("changed_files", "implementation_notes", mode="before")
    @classmethod
    def _coerce_list(cls, value):
        return as_string_list(value)

    @field_validator("requires_operator_approval", mode="before")
    @classmethod
    def _coerce_bool(cls, value):
        return as_bool(value)
