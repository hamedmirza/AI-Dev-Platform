
from app.agents.reviewer import ReviewerAgent
from app.graph.state import WorkflowState


def run_reviewer_node(agent: ReviewerAgent, request_text: str, state: WorkflowState):
    result = agent.review(request_text)
    state["stage"] = "reviewer"
    return result, state
