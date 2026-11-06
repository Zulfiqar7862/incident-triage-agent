"""Pull non-serializable runtime deps out of the LangGraph RunnableConfig."""

from __future__ import annotations

from typing import Any


def runtime_from(config: Any):
    """Accept RunnableConfig or a plain dict — LangGraph passes its own typed config."""
    cfg = config if isinstance(config, dict) else dict(config or {})
    rt = (cfg.get("configurable") or {}).get("runtime")
    if rt is None:
        raise RuntimeError("LangGraph configurable.runtime is missing")
    return rt
