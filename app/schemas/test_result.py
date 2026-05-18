
from pydantic import BaseModel, Field, field_validator

from app.schemas._coerce import as_bool, as_string_list


class TestResultResponse(BaseModel):
    """Tester output. ``commands`` and ``failures`` default to ``[]`` (e.g., docs profile)."""

    passed: bool
    summary: str
    commands: list[str] = Field(default_factory=list)
    failures: list[str] = Field(default_factory=list)

    @field_validator("passed", mode="before")
    @classmethod
    def _coerce_bool(cls, value):
        return as_bool(value)

    @field_validator("commands", "failures", mode="before")
    @classmethod
    def _coerce_list(cls, value):
        return as_string_list(value)
