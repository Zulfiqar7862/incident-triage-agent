"""Compile the incident-triage StateGraph."""

from __future__ import annotations

from typing import Any, Literal

from langgraph.graph import END, START, StateGraph

from app.application.agent.nodes import act_node, approval_node, input_node, prepare_node
from app.application.agent.state import AgentState


def _after_prepare(state: AgentState) -> Literal["act", "__end__"]:
    return "act" if state.get("route") == "act" else "__end__"


def _after_act(state: AgentState) -> Literal["prepare", "approval", "input", "__end__"]:
    route = state.get("route") or "continue"
    if route == "approval":
        return "approval"
    if route == "input":
        return "input"
    if route == "continue":
        return "prepare"
    return "__end__"


def _after_gate(state: AgentState) -> Literal["prepare", "__end__"]:
    return "prepare" if state.get("route") == "continue" else "__end__"


def build_agent_graph(checkpointer: Any = True):
    """Build and compile the agent graph."""
    g: StateGraph = StateGraph(AgentState)
    # LangGraph's NodeInputT is stricter than our plain-dict AgentState TypedDict.
    g.add_node("prepare", prepare_node)  # type: ignore[type-var]
    g.add_node("act", act_node)  # type: ignore[type-var]
    g.add_node("approval", approval_node)  # type: ignore[type-var]
    g.add_node("input", input_node)  # type: ignore[type-var]

    g.add_edge(START, "prepare")
    g.add_conditional_edges("prepare", _after_prepare, {"act": "act", "__end__": END})
    g.add_conditional_edges(
        "act",
        _after_act,
        {"prepare": "prepare", "approval": "approval", "input": "input", "__end__": END},
    )
    g.add_conditional_edges("approval", _after_gate, {"prepare": "prepare", "__end__": END})
    g.add_conditional_edges("input", _after_gate, {"prepare": "prepare", "__end__": END})

    if checkpointer is True:
        from langgraph.checkpoint.memory import MemorySaver

        return g.compile(checkpointer=MemorySaver())
    if checkpointer:
        return g.compile(checkpointer=checkpointer)
    return g.compile()


def graph_mermaid() -> str:
    """Static topology diagram for docs."""
    return (
        "```mermaid\n"
        "flowchart TD\n"
        "  START([START]) --> prepare\n"
        "  prepare -->|budget/control stop| END([END])\n"
        "  prepare -->|ok| act\n"
        "  act -->|continue| prepare\n"
        "  act -->|approval| approval\n"
        "  act -->|ask_operator| input\n"
        "  act -->|finished / needs_attention| END\n"
        "  approval -->|interrupt resume| prepare\n"
        "  input -->|interrupt resume| prepare\n"
        "```"
    )
