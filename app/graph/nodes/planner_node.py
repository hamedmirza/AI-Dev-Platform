
from app.agents.planner import PlannerAgent
from app.graph.state import WorkflowState


def run_planner_node(agent: PlannerAgent, request_text: str, state: WorkflowState):
    result = agent.plan(request_text)
    state["stage"] = "planner"
    return result, state
