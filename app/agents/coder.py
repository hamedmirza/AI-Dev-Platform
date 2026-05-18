
from app.agents.base import BaseAgent
from app.schemas.code_change import CodeChangeResponse


class CoderAgent(BaseAgent):
    def propose(self, request_text: str) -> CodeChangeResponse:
        user_prompt = (
            "Return JSON with changed_files, implementation_notes, requires_operator_approval, "
            "line_changes, and file_changes. Prefer line_changes for small edits; each item "
            "must contain path, operation, anchor, content, and optional occurrence. Use "
            "file_changes only for whole-file upsert/delete edits. Follow repository-specific "
            "constraints in the prompt (console FastAPI UI vs cloned app):\n\n"
            f"{request_text}"
        )
        return self.run(user_prompt, CodeChangeResponse)
