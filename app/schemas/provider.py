
from typing import Optional

from pydantic import BaseModel

from app.core.enums import ProviderStatus


class ProviderHealthResponse(BaseModel):
    provider: str
    status: ProviderStatus
    detail: str
    model: Optional[str] = None
