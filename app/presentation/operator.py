"""Typed, deterministic operator views built from tool identity and observed data.

Free-form model reasoning, logs, queries and errors are evidence, not UI copy.
Never attempt to clean them with string replacement. Unknown data gets an honest
fallback; raw payloads remain available through the existing audit/context APIs.
"""

from __future__ import annotations

import json
import math
import re
from collections.abc import Mapping, Sequence
from typing import Any, Literal, NotRequired, TypedDict

from app.domain.labels import status_words


class DisplayField(TypedDict):
    label: str
    value: str


class OperatorDisplay(TypedDict):
    state: NotRequired[Literal["applied", "rejected", "unverified", "failed"]]
    title: str
    summary: str
    fields: list[DisplayField]
    evidence: list[str]
    impact: str


TITLES = {
    "get_alert": "Review the incident",
    "list_services": "Check affected services",
    "describe_service": "Check service health",
    "query_metrics": "Check health measurements",
    "search_logs": "Review diagnostic evidence",
    "get_recent_deploys": "Review recent releases",
    "search_runbooks": "Check recovery guidance",
    "rollback_deploy": "Restore the previous version",
    "restart_service": "Restart the service",
    "update_working_memory": "Update the investigation plan",
    "ask_operator": "Request operator guidance",
    "finish": "Complete the investigation",
}
METRICS = {
    "error_rate": "Failed requests",
    "latency_p99": "Slowest requests",
    "cpu": "Processor use",
    "memory": "Memory use",
    "latency_p99_ms": "Slowest requests",
    "latency_p95_ms": "Slowest requests",
    "memory_usage_mb": "Memory use",
    "memory_usage_pct": "Memory use",
    "memory_mb": "Memory use",
    "memory_pct": "Memory use",
    "restarts": "Service restarts",
    "oom_kills": "Memory-related stops",
    "cpu_pct": "Processor use",
    "request_rate": "Requests per second",
}
STATUS_COPY = {
    "queued": "The investigation is queued.",
    "running": "Checking the incident and gathering evidence.",
    "awaiting_approval": "Review the proposed change before it can be applied.",
    "awaiting_input": "The investigation needs your guidance to continue.",
    "paused": "The investigation is paused. Resume when you are ready.",
    "interrupted": "The investigation was interrupted. Its recorded progress is saved.",
    "needs_attention": "The investigation needs attention. Review the evidence and provide guidance.",
    "completed": "The investigation is complete. Review the recorded outcome.",
    "failed": "The investigation stopped with an error. Progress is saved; review and retry when ready.",
    "cancelled": "The investigation was stopped. Already applied changes are not undone.",
}


def identifier(value: Any, *, version: bool = False) -> str:
    """Accept only the scalar identifier grammar, never arbitrary text as a label."""
    pattern = r"v?\d+(?:\.\d+){0,3}(?:-[a-z0-9.-]+)?" if version else r"[a-z0-9]+(?:[.-][a-z0-9]+)*"
    return value if isinstance(value, str) and re.fullmatch(pattern, value) else ""


def number(value: Any) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (float, int)) or not math.isfinite(value):
        return None
    return float(value)


def view(title: str, summary: str = "") -> OperatorDisplay:
    return {"title": title, "summary": summary, "fields": [], "evidence": [], "impact": ""}


def action_display(name: str, args: Mapping[str, Any]) -> OperatorDisplay:
    out = view(TITLES.get(name, "Review an investigation action"))
    for key, label in (("service", "Service"), ("to_version", "Restore version")):
        value = identifier(args.get(key), version=key == "to_version")
        if value:
            out["fields"].append({"label": label, "value": value})
    if name == "rollback_deploy":
        out["impact"] = (
            "Replaces this service’s running version. Requests may be briefly interrupted; recovery must be verified."
        )
    elif name == "restart_service":
        out["impact"] = (
            "Replaces the running service instances. Requests may be briefly interrupted. Recovery must be checked after the change."
        )
    return out


def decoded(content: Any) -> Any:
    if not isinstance(content, str):
        return content
    try:
        return json.loads(content)
    except (ValueError, TypeError):
        return None


def tool_result_display(name: str, args: Mapping[str, Any], content: Any, is_error: bool) -> OperatorDisplay:
    out = action_display(name, args)
    if is_error:
        out["summary"] = "This action could not be completed. No successful result was recorded."
        return out
    data = decoded(content)
    out["summary"] = "The result was recorded for the investigation."
    if name == "query_metrics" and isinstance(data, dict):
        metric = METRICS.get(str(data.get("metric")), "Service measurement")
        points = data.get("points")
        latest = (
            number(points[-1].get("value"))
            if isinstance(points, list) and points and isinstance(points[-1], dict)
            else None
        )
        baseline = number(data.get("baseline"))
        units = {"%": "%", "percent": "%", "ms": " ms", "MB": " MB", "MiB": " MiB", "count": "", "rps": " per second"}
        unit = units.get(str(data.get("unit")), "")
        if latest is not None:
            out["summary"] = f"{metric}: {latest:g}{unit}."
            if baseline is not None:
                out["summary"] += f" Usual level: {baseline:g}{unit}."
    elif name == "get_recent_deploys" and isinstance(data, dict):
        version = identifier(data.get("current_version"), version=True)
        if version:
            out["summary"] = f"Release reviewed: {version}."
        releases = data.get("deploys")
        if isinstance(releases, list) and releases and isinstance(releases[0], dict):
            age = number(releases[0].get("minutes_ago"))
            if age is not None and age >= 0:
                out["summary"] += f" The latest release was {age:g} minutes before this investigation."
    elif name == "describe_service" and isinstance(data, dict):
        count = number(data.get("replicas"))
        out["summary"] = (
            f"The service has {count:g} configured instances."
            if count is not None
            else "Service details were retrieved."
        )
    elif name == "list_services" and isinstance(data, list):
        out["summary"] = f"Retrieved details for {len(data)} services."
    elif name == "search_logs":
        out["summary"] = (
            "Recent service diagnostics were retrieved. Their contents are available in the engineering record."
        )
    elif name == "search_runbooks":
        out["summary"] = "Recovery guidance was retrieved for review."
    elif name == "get_alert" and isinstance(data, dict):
        out["summary"] = (
            "The incident alert is still active."
            if data.get("status") == "firing"
            else "The incident alert was retrieved."
        )
    elif name in ("rollback_deploy", "restart_service") and isinstance(data, dict) and data.get("ok") is True:
        out["summary"] = "The approved change was applied."
    return out


def calls_by_id(history: Sequence[dict]) -> dict[str, dict]:
    return {str(c.get("id")): c for m in history for c in m.get("tool_calls", []) if isinstance(c, dict)}


def observations(history: Sequence[dict], *, through_step: int | None = None, decision: bool = False) -> list[str]:
    calls = calls_by_id(history)
    # Keep the latest observed result per tool/service/measurement, not model diagnoses.
    facts: dict[tuple, str] = {}
    for message in history:
        if message.get("role") != "tool" or message.get("is_error"):
            continue
        if through_step is not None and message.get("step", 0) > through_step:
            continue
        name = str(message.get("name", ""))
        if name not in {"query_metrics", "get_recent_deploys", "describe_service", "search_logs", "search_runbooks"}:
            continue
        if decision and name not in {"query_metrics", "get_recent_deploys"}:
            continue
        call = calls.get(str(message.get("tool_call_id")), {})
        args = call.get("args", {})
        display = tool_result_display(name, args, message.get("content"), False)
        svc = identifier(args.get("service"))
        fact = display["summary"]
        if svc:
            fact = f"{svc}: {fact}"
        facts[(name, svc, str(args.get("metric", "")))] = fact
    return list(facts.values())


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


def event_display(event: Mapping[str, Any], st: Mapping[str, Any]) -> OperatorDisplay | None:
    kind, p = event["type"], event["payload"]
    history = st.get("history") or []
    calls = calls_by_id(history)
    if kind in {"tool.call", "tool.result"}:
        call = calls.get(str(p.get("id")), {})
        name = str(p.get("name") or call.get("name") or "")
        args = p.get("args", call.get("args", {}))
        if name in {"update_working_memory", "ask_operator", "finish"}:
            return None
        if kind == "tool.call":
            return action_display(name, args)
        if name in {"rollback_deploy", "restart_service"}:
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
        return tool_result_display(name, args, p.get("content"), bool(p.get("is_error")))
    if kind == "run.finished":
        return report_display(p.get("result", {}), history, st.get("env", {}).get("applied", {}))
    if kind == "approval.decided":
        approved = p.get("decision") == "approved"
        out = view("Change approved" if approved else "Change rejected")
        out["summary"] = "The operator's decision was saved" + (" with edits." if p.get("edited") else ".")
        if not approved:
            out["summary"] += " The proposed change was not applied. Any feedback was saved for the agent."
        return out
    if kind == "operator.control":
        return view(
            {"pause": "Pause requested", "resume": "Investigation resumed", "cancel": "Investigation stopped"}.get(
                p.get("action"), "Operator control recorded"
            )
        )
    if kind == "operator.message":
        return view("Operator guidance received", "The message was saved for the agent to read.")
    if kind == "policy.blocked":
        return view(
            "Proposed action blocked", "The change did not meet the confidence or scope policy. It was not applied."
        )
    if kind == "security.injection_flagged":
        return view(
            "Untrusted instructions detected",
            "Diagnostic evidence was flagged for review and was not treated as operator instructions.",
        )
    if kind == "run.status" and p.get("status") in {"failed", "paused", "interrupted", "cancelled", "needs_attention"}:
        status = p["status"]
        return view(status_words(status), STATUS_COPY[status])
    if kind == "llm.retry":
        return view("Connection retry", "The agent is retrying a temporarily unavailable service.")
    if kind == "run.created":
        return view("Investigation started")
    # No raw thought blobs, repeated waiting notices, or model-only assertions.
    return None


def present_event(event: dict, st: Mapping[str, Any]) -> dict:
    # Top-level projection is deliberately OUTSIDE the hash-chained payload.
    return {**event, "operator": event_display(event, st)}


def error_display(status: int) -> OperatorDisplay:
    title, summary = {
        404: ("Run not found", "This investigation could not be found. Select another or start a new one."),
        409: ("Decision already handled", "The investigation has moved on. Refresh its state before trying again."),
        422: (
            "Review your entries",
            "One or more fields could not be accepted. Review the edited fields and try again.",
        ),
        429: ("Please wait", "The service cannot accept more work right now. Try again shortly."),
    }.get(status, ("Service unavailable", "The request could not be completed. Please try again."))
    return view(title, summary)
