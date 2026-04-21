
from app.agents.tester import TesterAgent
from app.graph.state import WorkflowState


def run_tester_node(agent: TesterAgent, request_text: str, state: WorkflowState):
    result = agent.validate(request_text)
    state["stage"] = "tester"
    return result, state
