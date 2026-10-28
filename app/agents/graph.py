from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, START, StateGraph

from app.agents.nodes.leave_agent import NO, YES, confirm_node, leave_node, norm
from app.agents.nodes.policy_rag import policy_node
from app.agents.nodes.router import router_node
from app.agents.state import HRState


def begin_node(state: HRState) -> dict:
    # clear last turn's outputs, because the checkpointer keeps state between messages
    return {"answer": "", "citations": [], "retrieved": []}


def entry_route(state: HRState) -> str:
    if state.get("pending_action") and norm(state["question"]) in (YES | NO):
        return "confirm"
    return "router"


def fallback_node(state: HRState) -> dict:
    return {"answer": "I can help with HR policy questions and your leave. Could you rephrase?"}


def pick_route(state: HRState) -> str:
    return state["intent"]


def build_graph(checkpointer=None):
    g = StateGraph(HRState)
    g.add_node("begin", begin_node)
    g.add_node("router", router_node)
    g.add_node("policy", policy_node)
    g.add_node("leave", leave_node)
    g.add_node("confirm", confirm_node)
    g.add_node("fallback", fallback_node)

    g.add_edge(START, "begin")
    g.add_conditional_edges("begin", entry_route, {"confirm": "confirm", "router": "router"})
    g.add_conditional_edges("router", pick_route,
                            {"policy": "policy", "leave": "leave", "other": "fallback"})
    for step in ("policy", "leave", "confirm", "fallback"):
        g.add_edge(step, END)

    return g.compile(checkpointer=checkpointer or MemorySaver())