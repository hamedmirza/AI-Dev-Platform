
from app.agents.base import BaseAgent
from app.schemas.review import ReviewResponse


class ReviewerAgent(BaseAgent):
    def review(self, request_text: str) -> ReviewResponse:
        user_prompt = (
            "Review the proposed work for this task. Return JSON with approved, summary, "
            f"and issues:\n\n{request_text}"
        )
        return self.run(user_prompt, ReviewResponse)
