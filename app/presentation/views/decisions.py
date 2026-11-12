"""Operator cards for a pending decision: an approval or a question from the agent."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from app.presentation.views.display import OperatorDisplay, action_display, observations
from app.presentation.views.tool_labels import present_tool


def pending_display(pending: Mapping[str, Any], history: Sequence[dict] = ()) -> OperatorDisplay:
    raw_args = pending.get("args")
    args = raw_args if isinstance(raw_args, dict) else {}
    out = action_display(str(pending.get("tool", "")), args)
    out["summary"] = "Proposed from observed evidence; the cause is not independently confirmed."
    if pending.get("kind") == "input":
        out["summary"] = (
            "The agent needs your guidance. Read its full question in the engineering record before responding."
        )
    out["evidence"] = observations(history, through_step=pending.get("step"), decision=True)
    if not out["evidence"]:
        out["evidence"] = observations(history, through_step=pending.get("step"))
    if not out["evidence"]:
        out["evidence"] = [
            "No structured observations are available in this view. Review the engineering record before deciding."
        ]
    return out


def enrich_pending(pending: dict[str, Any]) -> dict[str, Any]:
    """Attach title/summary to a pending approval/input dict (mutates a copy)."""
    out = dict(pending)
    name = str(out.get("tool") or "")
    args = out.get("args") if isinstance(out.get("args"), dict) else {}
    ui = present_tool(name, args)
    out.setdefault("title", ui["title"])
    out.setdefault("summary", ui["summary"])
    out.setdefault("risk", ui["risk"])
    out["operator"] = pending_display(out)
    return out
