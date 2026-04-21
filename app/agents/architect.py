
from app.agents.base import BaseAgent
from app.schemas.architecture import ArchitectureResponse


class ArchitectAgent(BaseAgent):
    def design(self, request_text: str) -> ArchitectureResponse:
        user_prompt = (
            "Given this task, return JSON with touched_modules, file_change_plan, "
            f"dependency_notes, and migration_notes:\n\n{request_text}"
        )
        return self.run(user_prompt, ArchitectureResponse)
