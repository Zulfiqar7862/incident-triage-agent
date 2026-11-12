"""Operator wording for audit events, chosen through a registry keyed by event type.

The projection sits outside the hash-chained payload, so the audit record is unchanged.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from typing import Any

from app.domain.labels import status_words
from app.presentation.views.display import (
    STATUS_COPY,
    OperatorDisplay,
    action_display,
    calls_by_id,
    tool_result_display,
    view,
)
from app.presentation.views.report import report_display

EventView = Callable[[str, Mapping[str, Any], Mapping[str, Any]], OperatorDisplay | None]
"""(event type, payload, run state) -> operator display, or None to hide the event."""

PRODUCTION_CHANGES = {"rollback_deploy", "restart_service"}
AGENT_BOOKKEEPING = {"update_working_memory", "ask_operator", "finish"}
OPERATOR_VISIBLE_STATUSES = {"failed", "paused", "interrupted", "cancelled", "needs_attention"}


def _tool_view(kind: str, p: Mapping[str, Any], st: Mapping[str, Any]) -> OperatorDisplay | None:
    call = calls_by_id(st.get("history") or []).get(str(p.get("id")), {})
    name = str(p.get("name") or call.get("name") or "")
    args = p.get("args", call.get("args", {}))
    if name in AGENT_BOOKKEEPING:
        return None
    if kind == "tool.call":
        return action_display(name, args)
    if name in PRODUCTION_CHANGES:
        return _production_change_view(name, args, p, st)
    return tool_result_display(name, args, p.get("content"), bool(p.get("is_error")))


def _production_change_view(
    name: str, args: Mapping[str, Any], p: Mapping[str, Any], st: Mapping[str, Any]
) -> OperatorDisplay:
    """Only the structured apply record proves a change landed; the model's words do not."""
    recorded = st.get("env", {}).get("applied", {}).get(str(p.get("id")))
    if recorded and recorded.get("result", {}).get("ok") is True:
        out = tool_result_display(name, recorded.get("args", {}), recorded["result"], False)
        out["state"] = "applied"
        return out
    rejected = any(
        item.get("decision") == "rejected" and item.get("tool") == name and item.get("step") == p.get("step")
        for item in st.get("operator_log", [])
    )
    out = action_display(name, args)
    out["state"] = "rejected" if rejected else "failed" if p.get("is_error") else "unverified"
    out["summary"] = (
        "The operator rejected this change. It was not applied."
        if rejected
        else "No successful application of this change is confirmed in the structured record."
    )
    return out


def _finished_view(kind: str, p: Mapping[str, Any], st: Mapping[str, Any]) -> OperatorDisplay:
    return report_display(p.get("result", {}), st.get("history") or [], st.get("env", {}).get("applied", {}))


def _decision_view(kind: str, p: Mapping[str, Any], st: Mapping[str, Any]) -> OperatorDisplay:
    approved = p.get("decision") == "approved"
    out = view("Change approved" if approved else "Change rejected")
    out["summary"] = "The operator's decision was saved" + (" with edits." if p.get("edited") else ".")
    if not approved:
        out["summary"] += " The proposed change was not applied. Any feedback was saved for the agent."
    return out


def _control_view(kind: str, p: Mapping[str, Any], st: Mapping[str, Any]) -> OperatorDisplay:
    titles = {"pause": "Pause requested", "resume": "Investigation resumed", "cancel": "Investigation stopped"}
    return view(titles.get(str(p.get("action")), "Operator control recorded"))


def _status_view(kind: str, p: Mapping[str, Any], st: Mapping[str, Any]) -> OperatorDisplay | None:
    status = p.get("status")
    if status not in OPERATOR_VISIBLE_STATUSES:
        return None
    return view(status_words(status), STATUS_COPY[status])


def _fixed(title: str, summary: str = "") -> EventView:
    return lambda kind, p, st: view(title, summary)


EVENT_VIEWS: dict[str, EventView] = {
    "tool.call": _tool_view,
    "tool.result": _tool_view,
    "run.finished": _finished_view,
    "approval.decided": _decision_view,
    "operator.control": _control_view,
    "operator.message": _fixed("Operator guidance received", "The message was saved for the agent to read."),
    "policy.blocked": _fixed(
        "Proposed action blocked", "The change did not meet the confidence or scope policy. It was not applied."
    ),
    "security.injection_flagged": _fixed(
        "Untrusted instructions detected",
        "Diagnostic evidence was flagged for review and was not treated as operator instructions.",
    ),
    "run.status": _status_view,
    "llm.retry": _fixed("Connection retry", "The agent is retrying a temporarily unavailable service."),
    "run.created": _fixed("Investigation started"),
}
"""Registry: event type -> view. Unlisted types (raw thoughts, waiting notices) stay hidden."""


def event_display(event: Mapping[str, Any], st: Mapping[str, Any]) -> OperatorDisplay | None:
    """Operator wording for one event, or None when the event is not shown to operators."""
    handler = EVENT_VIEWS.get(event["type"])
    return handler(event["type"], event["payload"], st) if handler else None


def present_event(event: dict, st: Mapping[str, Any]) -> dict:
    """Attach the projection next to (not inside) the hash-chained payload."""
    return {**event, "operator": event_display(event, st)}
