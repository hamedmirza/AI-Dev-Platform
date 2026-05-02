from app.agents.base import BaseAgent
from app.schemas.ui_design import UIDesignResponse


class UIDesignerAgent(BaseAgent):
    def design(self, request_text: str) -> UIDesignResponse:
        user_prompt = (
            "Return JSON with design_summary, visual_system, layout_plan, interaction_notes, "
            "accessibility_notes, and implementation_notes for this UI/frontend task:\n\n"
            f"{request_text}"
        )
        return self.run(user_prompt, UIDesignResponse)
