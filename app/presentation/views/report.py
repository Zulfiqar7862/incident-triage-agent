"""Operator views of a run and its final incident report (verified data only)."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from app.presentation.views.display import (
    STATUS_COPY,
    OperatorDisplay,
    action_display,
    calls_by_id,
    decoded,
    identifier,
    observations,
    view,
)


def report_display(
    result: Mapping[str, Any], history: Sequence[dict] = (), applied: Mapping[str, Any] | None = None
) -> OperatorDisplay:
    resolved = result.get("resolved") is True
    out = view(
        "Incident resolved" if resolved else "Investigation finished",
        "The agent marked this incident resolved." if resolved else "The agent finished without confirming recovery.",
    )
    out["evidence"] = observations(history)
    out["fields"] = [{"label": "Cause", "value": "Not independently confirmed"}]
    for recorded in reversed(list((applied or {}).values())):
        if recorded.get("result", {}).get("ok") is True:
            action = action_display(recorded.get("tool", ""), recorded.get("args", {}))
            out["fields"] += [{"label": "Applied change", "value": action["title"]}, *action["fields"]]
            return out
    calls = calls_by_id(history)
    for m in reversed(history):
        if m.get("role") != "tool" or m.get("is_error") or m.get("name") not in {"rollback_deploy", "restart_service"}:
            continue
        data = decoded(m.get("content"))
        if not isinstance(data, dict) or data.get("ok") is not True:
            continue
        call = calls.get(str(m.get("tool_call_id")), {})
        action = action_display(str(m["name"]), call.get("args", {}))
        out["fields"] += [{"label": "Applied change", "value": action["title"]}, *action["fields"]]
        break
    return out


def run_display(st: Mapping[str, Any]) -> dict[str, Any]:
    history = st.get("history") or []
    svc = identifier(st.get("service"))
    return {
        "title": "Service disruption" + (f" · {svc}" if svc else ""),
        "summary": "Investigate the alert, review the evidence, and verify recovery before closing the incident.",
        "status": STATUS_COPY.get(str(st.get("status")), "Review the investigation state."),
        "evidence": observations(history),
        "plan": [
            "Review the alert and affected services",
            "Gather health and release evidence",
            "Review any proposed change",
            "Check recovery and record the outcome",
        ]
        if st.get("plan")
        else [],
        "report": report_display(st["result"], history, st.get("env", {}).get("applied", {}))
        if st.get("result")
        else None,
    }


def present_report(
    result: Mapping[str, Any], history: list[dict] | None = None, applied: Mapping[str, Any] | None = None
) -> dict[str, Any]:
    """Add a verified-data projection; never rewrite arbitrary model text."""
    display = report_display(result, history or [], applied)
    applied_label = next(
        (f["value"] for f in display["fields"] if f["label"] == "Applied change"), "No verified change recorded"
    )
    return {**result, "operator": display, "operator_summary": display["summary"], "fix_summary": applied_label}
