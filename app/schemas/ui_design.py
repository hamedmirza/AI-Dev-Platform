from pydantic import BaseModel, field_validator

from app.schemas._coerce import as_string_list


class UIDesignResponse(BaseModel):
    design_summary: str
    visual_system: list[str]
    layout_plan: list[str]
    interaction_notes: list[str]
    accessibility_notes: list[str]
    implementation_notes: list[str]

    @field_validator(
        "visual_system",
        "layout_plan",
        "interaction_notes",
        "accessibility_notes",
        "implementation_notes",
        mode="before",
    )
    @classmethod
    def _coerce_list(cls, value):
        return as_string_list(value)
