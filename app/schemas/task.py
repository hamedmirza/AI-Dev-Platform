
from datetime import datetime

from pydantic import BaseModel, Field


class TaskCreate(BaseModel):
    title: str = Field(min_length=3, max_length=255)
    request_text: str = Field(min_length=10)


class TaskCreated(BaseModel):
    task_id: str
    run_id: str
    created_at: datetime
