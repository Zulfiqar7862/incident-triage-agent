"""Operator-facing labels for tools. Additive UI fields only — LLM schemas unchanged."""
from __future__ import annotations

from collections.abc import Callable, Mapping
from typing import Any

from .specs import TOOLS, ToolSpec


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
        "risk": "high" if (kind or (spec.kind if spec else "")) == "write" else "low",
    }


def enrich_pending(pending: dict[str, Any]) -> dict[str, Any]:
    """Attach title/summary to a pending approval/input dict (mutates a copy)."""
    out = dict(pending)
    name = str(out.get("tool") or "")
    args = out.get("args") if isinstance(out.get("args"), dict) else {}
    ui = present_tool(name, args)
    out.setdefault("title", ui["title"])
    out.setdefault("summary", ui["summary"])
    out.setdefault("risk", ui["risk"])
    return out


SEVERITY_WORDS = {
    "P1": "Critical",
    "P2": "High",
    "P3": "Medium",
    "P4": "Low",
    "SEV1": "Critical",
    "SEV2": "High",
    "SEV3": "Medium",
    "SEV4": "Low",
    "CRITICAL": "Critical",
    "HIGH": "High",
    "MEDIUM": "Medium",
    "LOW": "Low",
}

STATUS_WORDS = {
    "queued": "Queued",
    "running": "Investigating",
    "awaiting_approval": "Needs your approval",
    "awaiting_input": "Needs your answer",
    "paused": "Paused",
    "interrupted": "Interrupted",
    "needs_attention": "Needs attention",
    "completed": "Finished",
    "failed": "Failed",
    "cancelled": "Stopped",
}


def severity_words(raw: str | None) -> str | None:
    if not raw:
        return None
    return SEVERITY_WORDS.get(raw.upper()) or SEVERITY_WORDS.get(raw) or None


def status_words(status: str) -> str:
    return STATUS_WORDS.get(status) or status.replace("_", " ").title()


def config_key_words(key: str) -> str:
    """DB_POOL_SIZE → database connection pool size (generic, not scenario-specific)."""
    known = {
        "DB_POOL_SIZE": "database connection pool size",
        "DB_POOL_TIMEOUT_MS": "database connection pool timeout",
        "HTTP_CLIENT_TIMEOUT_MS": "HTTP client timeout",
        "FEATURE_ONE_CLICK": "one-click checkout feature flag",
    }
    if key in known:
        return known[key]
    return key.replace("_", " ").lower()


def plain_task_from_alert(alert: Mapping[str, Any]) -> str:
    """Operator-facing task line without alert ids or P-codes."""
    service = _s(alert, "service") or "a service"
    title = _s(alert, "title")
    sev = severity_words(_s(alert, "severity")) or "elevated"
    if title:
        # Strip leading "service-name " duplication if present
        t = title
        if t.lower().startswith(service.lower()):
            t = t[len(service) :].lstrip(" :-")
        return f"{sev} priority on {service}: {t}. Investigate, find the root cause, remediate safely, and verify."
    return f"{sev} priority alert on {service}. Investigate, find the root cause, remediate safely, and verify."


def alert_card(alert: Mapping[str, Any], *, fired_at: float | None = None) -> dict[str, Any]:
    """Structured alert card for the operator console."""
    sev_raw = _s(alert, "severity")
    return {
        "title": _s(alert, "title") or "Production alert",
        "summary": plain_task_from_alert(alert),
        "service": _s(alert, "service"),
        "severity": severity_words(sev_raw) or sev_raw or "Unknown",
        "severity_code": sev_raw,  # engineers only; UI should prefer severity
        "fired_min_ago": alert.get("fired_min_ago"),
        "fired_at": fired_at,
    }
