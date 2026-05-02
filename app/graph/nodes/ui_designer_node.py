from app.agents.ui_designer import UIDesignerAgent
from app.graph.state import WorkflowState


def run_ui_designer_node(agent: UIDesignerAgent, request_text: str, state: WorkflowState):
    output = agent.design(request_text)
    state["stage"] = "ui_designer"
    state["ui_design_output"] = output.model_dump_json()
    return state
