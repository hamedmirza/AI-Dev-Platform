
from datetime import datetime

from pydantic import BaseModel, Field, model_validator


class TaskCreate(BaseModel):
    title: str = Field(min_length=3, max_length=255)
    description: str | None = Field(default=None, min_length=10)
    workspace_path: str | None = None
    task_type: str | None = None
    constraints: list[str] = Field(default_factory=list)
    target_files: list[str] = Field(default_factory=list)
    provider: str | None = None
    model: str | None = None
    request_text: str | None = Field(default=None, min_length=10)

    @model_validator(mode="after")
    def validate_request_fields(self) -> "TaskCreate":
        if not self.request_text and not self.description:
            raise ValueError("Either request_text or description is required.")

        if self.request_text is None and self.description is not None:
            self.request_text = self.description

        return self

    def to_prompt_text(self) -> str:
        lines = [f"Title: {self.title}"]
        if self.description:
            lines.extend(["Description:", self.description])
        elif self.request_text:
            lines.extend(["Description:", self.request_text])
        if self.workspace_path:
            lines.append(f"Workspace path: {self.workspace_path}")
        if self.task_type:
            lines.append(f"Task type: {self.task_type}")
        if self.constraints:
            lines.append("Constraints:")
            lines.extend(f"- {item}" for item in self.constraints)
        if self.target_files:
            lines.append("Target files:")
            lines.extend(f"- {item}" for item in self.target_files)
        if self.provider:
            lines.append(f"Provider override: {self.provider}")
        if self.model:
            lines.append(f"Model override: {self.model}")
        return "\n".join(lines)


class TaskCreated(BaseModel):
    task_id: str
    run_id: str
    created_at: datetime
