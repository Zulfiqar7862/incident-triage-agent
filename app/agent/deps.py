"""Pull non-serializable runtime deps out of the LangGraph RunnableConfig."""
from __future__ import annotations

from typing import Any


def runtime_from(config: dict[str, Any]):
    rt = (config.get("configurable") or {}).get("runtime")
    if rt is None:
        raise RuntimeError("LangGraph configurable.runtime is missing")
    return rt
