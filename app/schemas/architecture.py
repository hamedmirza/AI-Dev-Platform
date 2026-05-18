
from pydantic import BaseModel, Field, field_validator

from app.schemas._coerce import as_string_list


class ArchitectureResponse(BaseModel):
    """Architect output. ``file_change_plan`` is structural; the other lists are advisory."""

    touched_modules: list[str] = Field(default_factory=list)
    file_change_plan: list[str]
    dependency_notes: list[str] = Field(default_factory=list)
    migration_notes: list[str] = Field(default_factory=list)

    @field_validator(
        "touched_modules",
        "file_change_plan",
        "dependency_notes",
        "migration_notes",
        mode="before",
    )
    @classmethod
    def _coerce_list(cls, value):
        return as_string_list(value)
