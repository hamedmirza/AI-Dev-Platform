
from datetime import datetime

from pydantic import BaseModel


class ArtifactResponse(BaseModel):
    id: int
    artifact_type: str
    title: str
    content: str
    truncated: bool
    created_at: datetime
