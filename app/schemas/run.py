
from datetime import datetime
from typing import Optional

from pydantic import BaseModel


class TaskSummaryResponse(BaseModel):
    id: str
    title: str
    description: Optional[str]
    workspace_path: Optional[str]
    task_type: Optional[str]
    constraints: list[str]
    target_files: list[str]
    provider_override: Optional[str]
    model_override: Optional[str]
    request_text: str
    validation_profile: str = "auto"
    created_at: datetime
    created_at_human: str


class RunBlockerResponse(BaseModel):
    type: str
    message: str
    command: Optional[str] = None
    failed_path: Optional[str] = None
    returncode: Optional[int] = None
    stdout_excerpt: Optional[str] = None
    stderr_excerpt: Optional[str] = None
    affected_files: list[str] = []
    retry_eligible: bool = True
    suggested_retry_instruction: Optional[str] = None
    is_scope_mismatch: bool = False
    profile: Optional[str] = None


class RunStateSnapshotResponse(BaseModel):
    id: int
    stage: str
    status: str
    retry_count: int
    payload_json: str
    created_at: datetime


class RunResponse(BaseModel):
    id: str
    task_id: str
    status: str
    current_stage: str
    provider_name: str
    request_id: Optional[str]
    retry_count: int
    validation_profile: str = "auto"
    active_blocker: Optional[RunBlockerResponse] = None
    error_message: Optional[str]
    created_at: datetime
    updated_at: datetime
    created_at_human: str
    updated_at_human: str
    task: TaskSummaryResponse
    latest_state: Optional[RunStateSnapshotResponse] = None


class RunEventResponse(BaseModel):
    id: int
    event_type: str
    message: str
    payload_json: Optional[str]
    created_at: datetime


class RunActionRequest(BaseModel):
    note: Optional[str] = None


class RunActionResponse(BaseModel):
    run_id: str
    status: str
    message: str


class RunHistoryCleanupResponse(BaseModel):
    deleted_runs: int
    deleted_tasks: int
    cleaned_workspaces: int
    kept_terminal_runs: int
    message: str
