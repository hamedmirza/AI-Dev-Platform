
from pydantic import BaseModel


class ArchitectureResponse(BaseModel):
    touched_modules: list[str]
    file_change_plan: list[str]
    dependency_notes: list[str]
    migration_notes: list[str]
