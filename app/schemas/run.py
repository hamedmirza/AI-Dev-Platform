
from datetime import datetime
from typing import Optional

from pydantic import BaseModel


class RunResponse(BaseModel):
    id: str
    task_id: str
    status: str
    current_stage: str
    provider_name: str
    error_message: Optional[str]
    created_at: datetime
    updated_at: datetime


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
