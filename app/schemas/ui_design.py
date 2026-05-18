from pydantic import BaseModel, Field, field_validator

from app.schemas._coerce import as_string_list


class UIDesignResponse(BaseModel):
    """UI designer output. ``layout_plan`` is structural; advisory lists default to empty."""

    design_summary: str
    visual_system: list[str] = Field(default_factory=list)
    layout_plan: list[str]
    interaction_notes: list[str] = Field(default_factory=list)
    accessibility_notes: list[str] = Field(default_factory=list)
    implementation_notes: list[str] = Field(default_factory=list)

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
