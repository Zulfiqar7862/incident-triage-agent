"""Prepare node: control flags, budgets, inbox drain."""
from __future__ import annotations

from typing import Any

from langchain_core.runnables import RunnableConfig


async def prepare_node(state: dict, config: RunnableConfig) -> dict[str, Any]:
    from app.agent.deps import runtime_from

    rt = runtime_from(config)
    run_id = state["run_id"]
    # Always load latest Store checkpoint so operator edits/inbox are visible.
    st = rt.get(run_id)
    st["route"] = "continue"

    ctl = rt._control.pop(run_id, None)
    if ctl == "cancel":
        rt._set_status(st, "cancelled", "Cancelled by operator")
        st["route"] = "stop"
        return st
    if ctl == "pause":
        rt._set_status(st, "paused", "Paused by operator at a step boundary")
        st["route"] = "stop"
        return st
    if st["step"] >= st["max_steps"]:
        rt._set_status(
            st,
            "needs_attention",
            f"Step budget of {st['max_steps']} used up without finishing. "
            "Review the trace, send guidance, and resume to grant 10 more steps.",
        )
        st["route"] = "stop"
        return st
    if st["usage"]["input_tokens"] + st["usage"]["output_tokens"] >= st["max_run_tokens"]:
        rt._set_status(st, "needs_attention", "Token budget for this run is used up. Resume to grant 50% more.")
        st["route"] = "stop"
        return st
    if rt.settings.max_run_cost_usd > 0 and st["usage"]["cost_usd"] >= st.get("max_run_cost_usd", rt.settings.max_run_cost_usd):
        rt._set_status(
            st,
            "needs_attention",
            f"Cost budget of ${st.get('max_run_cost_usd', rt.settings.max_run_cost_usd):.2f} "
            "for this run is used up. Resume to raise it 50%.",
        )
        st["route"] = "stop"
        return st

    if st["status"] != "running":
        rt._set_status(st, "running")
    rt._maybe_budget_alert(st)
    st["route"] = "act"
    rt.store.save(st)
    return st
