
from app.agents.architect import ArchitectAgent
from app.graph.state import WorkflowState


def run_architect_node(agent: ArchitectAgent, request_text: str, state: WorkflowState):
    result = agent.design(request_text)
    state["stage"] = "architect"
    return result, state
