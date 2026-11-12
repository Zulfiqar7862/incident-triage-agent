"""Prepare node: operator control flags and budget ceilings at every step boundary."""

from __future__ import annotations

from typing import Any

from langchain_core.runnables import RunnableConfig

from app.application.agent.deps import steps_from


async def prepare_node(state: dict, config: RunnableConfig) -> dict[str, Any]:
    """Stop on pause / cancel / exhausted budget; otherwise route to ``act``."""
    steps = steps_from(config)
    st = steps.load(state["run_id"])
    st["route"] = "continue"

    action = steps.take_control(st["run_id"])
    if action is not None and steps.apply_control(st, action):
        st["route"] = "stop"
        return st
    if steps.stop_if_over_budget(st):
        st["route"] = "stop"
        return st

    if st["status"] != "running":
        steps.set_status(st, "running")
    steps.maybe_budget_alert(st)
    st["route"] = "act"
    steps.save(st)
    return st
