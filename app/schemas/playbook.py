from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field


class PlaybookCreate(BaseModel):
    repo_key: str = Field(min_length=3, max_length=64)
    role: str = Field(min_length=2, max_length=64)
    content: str = Field(min_length=1, max_length=20000)
    proposed_by_run_id: Optional[str] = None


class PlaybookHumanConfirm(BaseModel):
    actor: str = Field(min_length=1, max_length=255)
    notes: Optional[str] = Field(default=None, max_length=2000)


class PlaybookHumanVeto(BaseModel):
    actor: str = Field(min_length=1, max_length=255)
    reason: str = Field(min_length=1, max_length=4000)


class PlaybookRow(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    repo_key: str
    role: str
    status: str
    supervisor_decision: Optional[str] = None
    supervisor_rationale: Optional[str] = None
    supervisor_merged_content: Optional[str] = None
    created_at: datetime


class LessonCreate(BaseModel):
    repo_key: str = Field(min_length=3, max_length=64)
    body: str = Field(min_length=1, max_length=4000)
    source_run_id: Optional[str] = None
