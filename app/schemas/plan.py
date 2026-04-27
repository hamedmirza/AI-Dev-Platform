
from pydantic import BaseModel, field_validator

from app.schemas._coerce import as_string_list


class PlanResponse(BaseModel):
    summary: str
    assumptions: list[str]
    risks: list[str]
    steps: list[str]
    acceptance_criteria: list[str]

    @field_validator("assumptions", "risks", "steps", "acceptance_criteria", mode="before")
    @classmethod
    def _coerce_list(cls, value):
        return as_string_list(value)
