"""Pull the step port out of the LangGraph ``RunnableConfig``."""

from __future__ import annotations

from typing import Any

from app.application.ports import AgentStepsPort


def steps_from(config: Any) -> AgentStepsPort:
    """Accept a ``RunnableConfig`` or a plain dict; ``GraphRunner`` puts the port under ``configurable.steps``."""
    cfg = config if isinstance(config, dict) else dict(config or {})
    steps = (cfg.get("configurable") or {}).get("steps")
    if steps is None:
        raise RuntimeError("LangGraph configurable.steps is missing")
    return steps
