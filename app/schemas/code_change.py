
from typing import Literal

from pydantic import BaseModel, Field, field_validator

from app.schemas._coerce import as_bool, as_string_list


class FileChange(BaseModel):
    path: str
    content: str = ""
    change_type: Literal["upsert", "delete"] = "upsert"


class LineChange(BaseModel):
    path: str
    operation: Literal["replace", "insert_after", "insert_before", "delete"]
    anchor: str
    content: str = ""
    occurrence: int = Field(default=1, ge=1)


class CodeChangeResponse(BaseModel):
    """Coder output. ``implementation_notes`` is advisory and defaults to ``[]``."""

    changed_files: list[str]
    implementation_notes: list[str] = Field(default_factory=list)
    requires_operator_approval: bool = True
    line_changes: list[LineChange] = Field(default_factory=list)
    file_changes: list[FileChange] = Field(default_factory=list)

    @field_validator("changed_files", "implementation_notes", mode="before")
    @classmethod
    def _coerce_list(cls, value):
        return as_string_list(value)

    @field_validator("requires_operator_approval", mode="before")
    @classmethod
    def _coerce_bool(cls, value):
        return as_bool(value)
