"""Act node: one model turn, then dispatch its tool calls and pick the next route."""

from __future__ import annotations

from typing import Any

from langchain_core.runnables import RunnableConfig

from app.application.agent.deps import steps_from


async def act_node(state: dict, config: RunnableConfig) -> dict[str, Any]:
    """Drain the inbox, call the model, run its tools, and route to prepare / a gate / END."""
    steps = steps_from(config)
    st = steps.load(state["run_id"])
    st["step"] += 1
    step = st["step"]
    acks = steps.drain_inbox(st, step)
    st["inbox_acks"] = acks

    resp = await steps.call_llm(st, steps.build_messages(st))
    steps.record_assistant(st, resp, step)
    if resp.tool_calls:
        route = steps.conclude(st, await steps.dispatch(st, resp.tool_calls, step))
    else:
        route = steps.nudge(st, step)

    st["route"] = route
    if route != "stop":
        steps.save(st)  # stop paths were already persisted by their status change
    steps.ack_inbox(acks)  # at-least-once: ack only after the messages are in a saved checkpoint
    return st
