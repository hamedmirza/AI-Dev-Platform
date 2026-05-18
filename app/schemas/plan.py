
from pydantic import BaseModel, Field, field_validator

from app.schemas._coerce import as_string_list


class PlanResponse(BaseModel):
    """Planner output.

    Structural fields (``summary``, ``steps``, ``acceptance_criteria``) are mandatory because
    they define the work. Advisory metadata fields (``assumptions``, ``risks``) default to
    an empty list — many trivial tasks (docs edits, single-line tweaks) genuinely have none,
    and leaner models legitimately omit empty fields from their JSON output.
    """

    summary: str
    assumptions: list[str] = Field(default_factory=list)
    risks: list[str] = Field(default_factory=list)
    steps: list[str]
    acceptance_criteria: list[str]

    @field_validator("assumptions", "risks", "steps", "acceptance_criteria", mode="before")
    @classmethod
    def _coerce_list(cls, value):
        return as_string_list(value)
