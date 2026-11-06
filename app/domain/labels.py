"""Operator-facing status / severity / alert shaping (pure functions)."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any


def _s(args: Mapping[str, Any], key: str) -> str:
    v = args.get(key)
    return "" if v is None else str(v).strip()


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
