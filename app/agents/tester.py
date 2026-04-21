
from app.agents.base import BaseAgent
from app.schemas.test_result import TestResultResponse


class TesterAgent(BaseAgent):
    def validate(self, request_text: str) -> TestResultResponse:
        user_prompt = (
            "Return JSON with passed, summary, commands, and failures describing the "
            f"validation strategy for this task:\n\n{request_text}"
        )
        return self.run(user_prompt, TestResultResponse)
