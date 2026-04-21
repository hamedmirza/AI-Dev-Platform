
from app.agents.base import BaseAgent
from app.schemas.plan import PlanResponse


class PlannerAgent(BaseAgent):
    def plan(self, request_text: str) -> PlanResponse:
        user_prompt = (
            "Return JSON with summary, assumptions, risks, steps, and acceptance_criteria "
            f"for this software task:\n\n{request_text}"
        )
        return self.run(user_prompt, PlanResponse)
