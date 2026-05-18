from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field


class ProjectCreate(BaseModel):
    name: str = Field(min_length=3, max_length=255)
    initial_requirements: str = Field(min_length=10)
    source_repo: Optional[str] = None
    app_type: Optional[str] = None
    validation_profile: str = "python"


class ProjectMessageCreate(BaseModel):
    content: str = Field(min_length=1, max_length=12000)


class ProjectQuestionAnswer(BaseModel):
    answer: str = Field(min_length=1, max_length=8000)


class ProjectSummary(BaseModel):
    id: str
    name: str
    slug: str
    status: str
    app_type: Optional[str]
    source_repo_spec: Optional[str]
    validation_profile: str
    readiness_score: int
    open_questions: int
    build_items: int
    active_runs: int
    created_at: datetime
    updated_at: datetime


class ProjectMessageResponse(BaseModel):
    id: int
    project_id: str
    role: str
    message_type: str
    content: str
    structured_json: str
    created_at: datetime


class ProjectQuestionResponse(BaseModel):
    id: int
    project_id: str
    key: str
    question: str
    reason: str
    answer_type: str
    options: list[str]
    status: str
    answer: Optional[str]
    created_at: datetime
    answered_at: Optional[datetime]


class ProjectBuildItemResponse(BaseModel):
    id: int
    project_id: str
    parent_id: Optional[int]
    title: str
    description: str
    item_type: str
    status: str
    target_files: list[str]
    depends_on: list[str]
    assigned_role: str
    run_id: Optional[str]
    created_at: datetime
    updated_at: datetime


class ProjectDetail(ProjectSummary):
    initial_requirements: str
    target_stack: dict[str, str]
    messages: list[ProjectMessageResponse]
    questions: list[ProjectQuestionResponse]
    build_items_detail: list[ProjectBuildItemResponse]


class ProjectCommandResponse(BaseModel):
    project: ProjectDetail
    message: str
    action: str
    run_id: Optional[str] = None
    run_ids: list[str] = Field(default_factory=list)
