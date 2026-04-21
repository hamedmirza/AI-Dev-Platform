
from app.agents.coder import CoderAgent
from app.graph.state import WorkflowState


def run_coder_node(agent: CoderAgent, request_text: str, state: WorkflowState):
    result = agent.propose(request_text)
    state["stage"] = "coder"
    return result, state
