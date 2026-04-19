
from pydantic import BaseModel


class ReviewResponse(BaseModel):
    approved: bool
    summary: str
    issues: list[str]
