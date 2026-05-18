
from app.agents.base import BaseAgent
from app.schemas.test_result import TestResultResponse


class TesterAgent(BaseAgent):
    def validate(self, request_text: str) -> TestResultResponse:
        user_prompt = (
            "Return JSON with passed, summary, commands, and failures describing the "
            "validation strategy for this task. commands must use only the selected "
            "validation profile commands provided in the request. Do not emit shell "
            f"pipelines or arbitrary commands:\n\n{request_text}"
        )
        return self.run(user_prompt, TestResultResponse)
