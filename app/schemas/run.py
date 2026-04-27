
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
    error_message: Optional[str]
    created_at: datetime
    updated_at: datetime
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
