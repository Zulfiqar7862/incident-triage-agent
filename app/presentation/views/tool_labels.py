"""Operator-facing labels for tools. Additive UI fields only — LLM schemas unchanged."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from typing import Any

from app.application.tools.specs import TOOLS, ToolSpec
from app.domain.labels import (
    SEVERITY_WORDS,
    STATUS_WORDS,
    alert_card,
    config_key_words,
    plain_task_from_alert,
    severity_words,
    status_words,
)
from app.domain.policy import risk_for_kind


def _s(args: Mapping[str, Any], key: str) -> str:
    v = args.get(key)
    return "" if v is None else str(v).strip()


def _metric_words(name: str) -> str:
    return name.replace("_", " ")


def _describe_get_alert(_a: Mapping[str, Any]) -> str:
    return "Read the alert that started this incident"


def _describe_list_services(_a: Mapping[str, Any]) -> str:
    return "List services and their health"


def _describe_describe_service(a: Mapping[str, Any]) -> str:
    svc = _s(a, "service")
    return f"Inspect {svc}" if svc else "Inspect a service"


def _describe_query_metrics(a: Mapping[str, Any]) -> str:
    svc, metric = _s(a, "service"), _s(a, "metric")
    if svc and metric:
        return f"Check {_metric_words(metric)} for {svc}"
    if svc:
        return f"Check health metrics for {svc}"
    return "Check service health metrics"


def _describe_search_logs(a: Mapping[str, Any]) -> str:
    svc, query = _s(a, "service"), _s(a, "query")
    if svc and query and query != "*":
        return f"Read recent logs for {svc} matching “{query}”"
    if svc:
        return f"Read recent error logs for {svc}"
    return "Read recent error logs"


def _describe_search_runbooks(a: Mapping[str, Any]) -> str:
    q = _s(a, "query")
    return f"Search runbooks for “{q}”" if q else "Search internal runbooks"


def _describe_get_recent_deploys(a: Mapping[str, Any]) -> str:
    svc = _s(a, "service")
    return f"Review recent deploys for {svc}" if svc else "Review recent deploys"


def _describe_rollback(a: Mapping[str, Any]) -> str:
    svc, ver = _s(a, "service"), _s(a, "to_version")
    if svc and ver:
        return f"Roll back {svc} to version {ver}"
    if svc:
        return f"Roll back {svc} to a previous version"
    return "Roll back a service to a previous version"


def _describe_restart(a: Mapping[str, Any]) -> str:
    svc = _s(a, "service")
    return f"Restart {svc}" if svc else "Restart a service"


def _describe_memory(_a: Mapping[str, Any]) -> str:
    return "Update the investigation notes"


def _describe_ask(a: Mapping[str, Any]) -> str:
    return _s(a, "question") or "Ask you a question"


def _describe_finish(_a: Mapping[str, Any]) -> str:
    return "Wrap up the incident report"


_DESCRIBERS: dict[str, Callable[[Mapping[str, Any]], str]] = {
    "get_alert": _describe_get_alert,
    "list_services": _describe_list_services,
    "describe_service": _describe_describe_service,
    "query_metrics": _describe_query_metrics,
    "search_logs": _describe_search_logs,
    "search_runbooks": _describe_search_runbooks,
    "get_recent_deploys": _describe_get_recent_deploys,
    "rollback_deploy": _describe_rollback,
    "restart_service": _describe_restart,
    "update_working_memory": _describe_memory,
    "ask_operator": _describe_ask,
    "finish": _describe_finish,
}

_LABELS: dict[str, str] = {
    "get_alert": "Alert details",
    "list_services": "Service list",
    "describe_service": "Service details",
    "query_metrics": "Health metrics",
    "search_logs": "Log search",
    "search_runbooks": "Runbook search",
    "get_recent_deploys": "Deploy history",
    "rollback_deploy": "Rollback",
    "restart_service": "Restart",
    "update_working_memory": "Notes update",
    "ask_operator": "Question for you",
    "finish": "Incident report",
}


def tool_label(name: str) -> str:
    if name in _LABELS:
        return _LABELS[name]
    return name.replace("_", " ").strip().title() or "Action"


def describe_tool(name: str, args: Mapping[str, Any] | None = None) -> str:
    args = args or {}
    fn = _DESCRIBERS.get(name)
    if fn:
        return fn(args)
    # Typed fallback without function-call syntax
    label = tool_label(name)
    svc = _s(args, "service")
    ver = _s(args, "to_version")
    if svc and ver:
        return f"{label} on {svc} to {ver}"
    if svc:
        return f"{label} for {svc}"
    return label


def present_tool(name: str, args: Mapping[str, Any] | None = None, *, kind: str | None = None) -> dict[str, str]:
    """Additive UI fields for events and approval payloads."""
    spec: ToolSpec | None = TOOLS.get(name)
    return {
        "title": tool_label(name),
        "summary": describe_tool(name, args),
        "category": kind or (spec.kind if spec else "unknown"),
        "risk": risk_for_kind(kind or (spec.kind if spec else "")),
    }


__all__ = [
    "tool_label",
    "describe_tool",
    "present_tool",
    "SEVERITY_WORDS",
    "STATUS_WORDS",
    "severity_words",
    "status_words",
    "config_key_words",
    "plain_task_from_alert",
    "alert_card",
]
