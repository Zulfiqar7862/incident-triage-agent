"""Human-in-the-loop gate nodes: LangGraph ``interrupt()`` + ``Command(resume=...)``.

The node pauses first; ``GraphRunner`` flips the Store status to awaiting_* only
after ``ainvoke`` returns, so the interrupt checkpoint is already durable when an
operator can see the gate. The decision itself is applied by ``GateResolver``.
"""

from __future__ import annotations

from typing import Any

from langchain_core.runnables import RunnableConfig
from langgraph.types import interrupt

from app.application.agent.deps import steps_from


async def approval_node(state: dict, config: RunnableConfig) -> dict[str, Any]:
    """Pause for an approve / reject decision, then apply it."""
    steps = steps_from(config)
    st = steps.load(state["run_id"])
    pending = st.get("pending") or state.get("pending")
    if not pending or pending.get("kind") != "approval":
        st["route"] = "continue"
        return st
    decision = interrupt(pending)
    st = steps.load(state["run_id"])
    steps.resolve_approval(st, st.get("pending") or pending, decision)
    return st


async def input_node(state: dict, config: RunnableConfig) -> dict[str, Any]:
    """Pause for the operator's answer to ``ask_operator``, then record it."""
    steps = steps_from(config)
    st = steps.load(state["run_id"])
    pending = st.get("pending") or state.get("pending")
    if not pending or pending.get("kind") != "input":
        st["route"] = "continue"
        return st
    decision = interrupt(pending)
    st = steps.load(state["run_id"])
    steps.resolve_answer(st, st.get("pending") or pending, decision)
    return st
