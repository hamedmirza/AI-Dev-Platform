
from pydantic import BaseModel, field_validator

from app.schemas._coerce import as_bool, as_string_list


class TestResultResponse(BaseModel):
    passed: bool
    summary: str
    commands: list[str]
    failures: list[str]

    @field_validator("passed", mode="before")
    @classmethod
    def _coerce_bool(cls, value):
        return as_bool(value)

    @field_validator("commands", "failures", mode="before")
    @classmethod
    def _coerce_list(cls, value):
        return as_string_list(value)
