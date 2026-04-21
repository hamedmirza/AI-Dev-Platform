
from app.agents.base import BaseAgent
from app.schemas.code_change import CodeChangeResponse


class CoderAgent(BaseAgent):
    def propose(self, request_text: str) -> CodeChangeResponse:
        user_prompt = (
            "Return JSON with changed_files, implementation_notes, and "
            f"requires_operator_approval for this task:\n\n{request_text}"
        )
        return self.run(user_prompt, CodeChangeResponse)
