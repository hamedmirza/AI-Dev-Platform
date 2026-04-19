
from pydantic import BaseModel


class TestResultResponse(BaseModel):
    passed: bool
    summary: str
    commands: list[str]
    failures: list[str]
