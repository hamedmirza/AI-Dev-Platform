from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field


class SourceRepoValidateRequest(BaseModel):
    source_repo: str = Field(min_length=1, max_length=2048)


class SourceRepoSaveRequest(SourceRepoValidateRequest):
    label: Optional[str] = Field(default=None, max_length=255)


class SourceRepoValidationResponse(BaseModel):
    source_repo_spec: str
    kind: str
    label: str
    valid: bool
    branch: Optional[str] = None
    head_sha: Optional[str] = None
    remotes: list[str] = Field(default_factory=list)
    dirty: Optional[bool] = None


class SavedSourceRepoResponse(SourceRepoValidationResponse):
    id: str
    repo_key: str
    status: str
    created_at: datetime
    updated_at: datetime
