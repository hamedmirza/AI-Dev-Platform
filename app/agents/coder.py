
from app.agents.base import BaseAgent
from app.schemas.code_change import CodeChangeResponse


class CoderAgent(BaseAgent):
    def propose(self, request_text: str) -> CodeChangeResponse:
        user_prompt = (
            "Return JSON with changed_files, implementation_notes, requires_operator_approval, "
            "line_changes, and file_changes. Prefer line_changes for small edits; each item "
            "must contain path, operation, anchor, content, and optional occurrence. Use "
            "file_changes only for whole-file upsert/delete edits. Preserve existing FastAPI "
            "APIRouter routes, route signatures, imports, auth/session behavior, redirects, "
            f"and UI flows unless explicitly asked to change them:\n\n{request_text}"
        )
        return self.run(user_prompt, CodeChangeResponse)
