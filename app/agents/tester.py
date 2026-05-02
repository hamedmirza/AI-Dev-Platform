
from app.agents.base import BaseAgent
from app.schemas.test_result import TestResultResponse


class TesterAgent(BaseAgent):
    def validate(self, request_text: str) -> TestResultResponse:
        user_prompt = (
            "Return JSON with passed, summary, commands, and failures describing the "
            "validation strategy for this task. commands must use only: ruff check ., "
            "mypy app, pytest -q, pytest tests -q, or pytest <test-path> -q. Do not emit "
            f"shell pipelines or arbitrary commands:\n\n{request_text}"
        )
        return self.run(user_prompt, TestResultResponse)
