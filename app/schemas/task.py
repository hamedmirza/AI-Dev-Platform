
from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel, Field, field_validator, model_validator

from app.core.exceptions import ConfigurationError
from app.core.settings import get_settings
from app.services.source_repo_policy import validate_source_repo_spec


class TaskCreate(BaseModel):
    title: str = Field(min_length=3, max_length=255)
    description: Optional[str] = Field(default=None, min_length=10)
    workspace_path: Optional[str] = None
    task_type: Optional[str] = None
    constraints: list[str] = Field(default_factory=list)
    target_files: list[str] = Field(default_factory=list)
    provider: Optional[str] = None
    model: Optional[str] = None
    request_text: Optional[str] = Field(default=None, min_length=10)
    source_repo: Optional[str] = None
    use_scout: bool = False
    stage_models: Optional[dict[str, str]] = None
    validation_profile: str = "auto"
    validation_commands: list[str] = Field(default_factory=list)

    @field_validator("validation_profile")
    @classmethod
    def validate_validation_profile(cls, value: str) -> str:
        profile = (value or "auto").strip().lower()
        allowed = {"auto", "python", "react-vite", "full-stack", "custom"}
        if profile not in allowed:
            raise ValueError(
                "validation_profile must be one of auto, python, react-vite, full-stack, custom."
            )
        return profile

    @field_validator("source_repo")
    @classmethod
    def validate_source_repo(cls, value: Optional[str]) -> Optional[str]:
        if value is None or not str(value).strip():
            return None
        spec = str(value).strip()
        try:
            validate_source_repo_spec(spec, get_settings())
        except ConfigurationError as exc:
            raise ValueError(str(exc)) from exc
        return spec

    @field_validator("stage_models")
    @classmethod
    def validate_stage_models(cls, value: Optional[dict[str, Any]]) -> Optional[dict[str, str]]:
        if not value:
            return None
        allowed = {
            "planner",
            "architect",
            "ui_designer",
            "coder",
            "reviewer",
            "tester",
            "supervisor",
        }
        out: dict[str, str] = {}
        for key, raw in value.items():
            k = str(key).strip().lower()
            if k not in allowed:
                raise ValueError(f"Unknown stage_models key: {key!r}.")
            if isinstance(raw, str) and raw.strip():
                out[k] = raw.strip()
        return out or None

    @field_validator("validation_commands")
    @classmethod
    def validate_validation_commands(cls, value: list[str]) -> list[str]:
        return [item.strip() for item in value if item.strip()]

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
        if self.source_repo:
            lines.append(f"Source repository: {self.source_repo}")
        if self.task_type:
            lines.append(f"Task type: {self.task_type}")
        if self.constraints:
            lines.append("Constraints:")
            lines.extend(f"- {item}" for item in self.constraints)
        if self.target_files:
            lines.append("Target files:")
            lines.extend(f"- {item}" for item in self.target_files)
        if self.validation_profile:
            lines.append(f"Validation profile: {self.validation_profile}")
        if self.validation_commands:
            lines.append("Validation commands:")
            lines.extend(f"- {item}" for item in self.validation_commands)
        if self.provider:
            lines.append(f"Provider override: {self.provider}")
        if self.model:
            lines.append(f"Model override: {self.model}")
        return "\n".join(lines)


class TaskCreated(BaseModel):
    task_id: str
    run_id: str
    request_id: Optional[str] = None
    created_at: datetime
