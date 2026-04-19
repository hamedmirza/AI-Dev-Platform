
from pydantic import BaseModel


class PlanResponse(BaseModel):
    summary: str
    assumptions: list[str]
    risks: list[str]
    steps: list[str]
    acceptance_criteria: list[str]
