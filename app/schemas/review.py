
from pydantic import BaseModel, field_validator

from app.schemas._coerce import as_bool, as_string_list


class ReviewResponse(BaseModel):
    approved: bool
    summary: str
    issues: list[str]

    @field_validator("approved", mode="before")
    @classmethod
    def _coerce_bool(cls, value):
        return as_bool(value)

    @field_validator("issues", mode="before")
    @classmethod
    def _coerce_list(cls, value):
        return as_string_list(value)
