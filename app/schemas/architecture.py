
from pydantic import BaseModel, field_validator

from app.schemas._coerce import as_string_list


class ArchitectureResponse(BaseModel):
    touched_modules: list[str]
    file_change_plan: list[str]
    dependency_notes: list[str]
    migration_notes: list[str]

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
