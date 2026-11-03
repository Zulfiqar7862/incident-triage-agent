"""Agent state schema shared by LangGraph and the Store checkpoint."""
from __future__ import annotations

import time
import uuid
from typing import Annotated, Any, NotRequired

from typing_extensions import TypedDict

from app.config import Settings


def _last(left: Any, right: Any) -> Any:
    """Last-write-wins reducer for state keys updated by a single node per step."""
    return right if right is not None else left


class AgentState(TypedDict):
    run_id: str
    scenario_id: str
    title: str
    service: str
    task: str
    status: Annotated[str, _last]
    status_reason: Annotated[str | None, _last]
    created_at: float
    step: Annotated[int, _last]
    max_steps: Annotated[int, _last]
    max_run_tokens: Annotated[int, _last]
    max_run_cost_usd: Annotated[float, _last]
    plan: Annotated[list, _last]
    hypotheses: Annotated[list, _last]
    notes: Annotated[list, _last]
    actions: Annotated[list, _last]
    operator_log: Annotated[list, _last]
    history: Annotated[list, _last]
    pending: Annotated[Any, _last]
    recalled_memories: Annotated[list, _last]
    env: Annotated[dict, _last]
    usage: Annotated[dict, _last]
    last_context: Annotated[Any, _last]
    compacted_groups: Annotated[int, _last]
    nudges: Annotated[int, _last]
    loop_guard: Annotated[dict, _last]
    budget_alerts: Annotated[list, _last]
    result: Annotated[Any, _last]
    error: Annotated[Any, _last]
    route: Annotated[str, _last]
    inbox_acks: Annotated[list, _last]
    checkpoint_version: NotRequired[Annotated[int, _last]]


def new_run_state(run_id: str, scenario: dict, settings: Settings) -> dict:
    a = scenario["alert"]
    return {
        "run_id": run_id,
        "scenario_id": scenario["id"],
        "title": scenario["title"],
        "service": a["service"],
        "task": (
            f"Alert {a['id']} ({a['severity']}) on {a['service']}: {a['title']}. "
            "Investigate, find the root cause, remediate safely, and verify."
        ),
        "status": "queued",
        "status_reason": None,
        "created_at": time.time(),
        "step": 0,
        "max_steps": settings.max_steps,
        "max_run_tokens": settings.max_run_tokens,
        "max_run_cost_usd": settings.max_run_cost_usd,
        "plan": [],
        "hypotheses": [],
        "notes": [],
        "actions": [],
        "operator_log": [],
        "history": [],
        "pending": None,
        "recalled_memories": [],
        "env": {},
        "usage": {
            "llm_calls": 0,
            "input_tokens": 0,
            "output_tokens": 0,
            "cost_usd": 0.0,
            "llm_ms": 0,
            "tool_calls": 0,
            "tool_retries": 0,
            "tool_errors": 0,
        },
        "last_context": None,
        "compacted_groups": 0,
        "nudges": 0,
        "loop_guard": {"counts": {}},
        "budget_alerts": [],
        "result": None,
        "error": None,
        "route": "continue",
        "inbox_acks": [],
    }


def make_run_id() -> str:
    return f"run-{uuid.uuid4().hex[:8]}"
