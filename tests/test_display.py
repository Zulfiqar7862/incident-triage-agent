"""Operator projections must not turn raw model/evidence text into UI prose."""

import json
import time
from copy import deepcopy

import pytest
from app.config import Settings
from app.llm.scripted import ScriptedPolicy
from app.main import create_app
from app.presentation.operator import (
    event_display,
    pending_display,
    present_event,
    present_report,
    report_display,
    run_display,
    tool_result_display,
)
from fastapi.testclient import TestClient

RAW = "DB_POOL_SIZE 50→5 ERROR POST /api/checkout TimeoutError rollback_deploy(service=x) Traceback"


def assert_plain(value):
    text = json.dumps(value)
    for fragment in ("DB_POOL_SIZE", "ERROR POST", "/api/checkout", "TimeoutError", "rollback_deploy(", "Traceback"):
        assert fragment not in text


def history():
    return [
        {
            "role": "assistant",
            "text": RAW,
            "tool_calls": [
                {
                    "id": "measure",
                    "name": "query_metrics",
                    "args": {"service": "checkout-service", "metric": "error_rate"},
                },
                {"id": "logs", "name": "search_logs", "args": {"service": "checkout-service", "query": RAW}},
            ],
        },
        {
            "role": "tool",
            "tool_call_id": "measure",
            "name": "query_metrics",
            "step": 2,
            "content": json.dumps(
                {"metric": "error_rate", "unit": "%", "points": [{"value": 14}], "baseline": 0.3, "raw": RAW}
            ),
        },
        {"role": "tool", "tool_call_id": "logs", "name": "search_logs", "step": 2, "content": RAW},
    ]


def test_pending_uses_observed_facts_not_model_reason_or_legacy_summary():
    pending = {
        "tool": "rollback_deploy",
        "step": 3,
        "summary": RAW,
        "args": {"service": "checkout-service", "to_version": "v2.13.2", "confidence": 0.85, "reason": RAW},
    }
    before = deepcopy(pending)
    display = pending_display(pending, history())
    assert_plain(display)
    assert display["title"] == "Restore the previous version"
    assert "checkout-service: Failed requests: 14%. Usual level: 0.3%." in display["evidence"]
    assert display["fields"][-1]["value"] == "v2.13.2"
    assert pending == before
    # Later recovery must not be presented as pre-approval evidence.
    later = history() + [
        {
            "role": "tool",
            "name": "query_metrics",
            "tool_call_id": "measure",
            "step": 8,
            "content": json.dumps({"metric": "error_rate", "unit": "%", "points": [{"value": 0.29}], "baseline": 0.3}),
        }
    ]
    assert pending_display(pending, later)["evidence"] == display["evidence"]


@pytest.mark.parametrize(
    "name,content,is_error",
    [
        ("search_logs", RAW, False),
        (
            "get_recent_deploys",
            json.dumps(
                {"changes": RAW, "current_version": "v2.14.0", "deploys": [{"changes": RAW, "minutes_ago": 23}]}
            ),
            False,
        ),
        ("query_metrics", RAW, True),
        ("unknown", RAW, False),
    ],
)
def test_tool_display_never_repeats_logs_queries_or_errors(name, content, is_error):
    assert_plain(tool_result_display(name, {"query": RAW, "reason": RAW}, content, is_error))


def test_report_does_not_parse_or_sanitize_arbitrary_model_text():
    result = {"resolved": True, "summary": RAW, "root_cause": RAW, "fix_applied": RAW}
    report = present_report(result, history())
    assert report["summary"] == RAW and report["root_cause"] == RAW and report["fix_applied"] == RAW
    assert_plain(report["operator"])
    assert_plain(report["operator_summary"])
    assert report["operator"]["fields"][0]["value"] == "Not independently confirmed"
    assert "operator" not in result


def test_rejected_edited_and_applied_actions_use_structured_records():
    applied = {
        "change": {
            "tool": "rollback_deploy",
            "args": {"service": "checkout-service", "to_version": "v2.13.1", "reason": RAW},
            "result": {"ok": True, "message": RAW},
        }
    }
    st = {"env": {"applied": applied}, "history": history()}
    display = event_display(
        {"type": "tool.result", "payload": {"id": "change", "name": "rollback_deploy", "content": RAW}}, st
    )
    assert_plain(display)
    assert display["state"] == "applied"
    assert display["fields"][-1]["value"] == "v2.13.1"
    report = report_display({"resolved": True, "root_cause": RAW}, history(), applied)
    assert any(field["value"] == "Restore the previous version" for field in report["fields"])
    rejected = event_display({"type": "approval.decided", "payload": {"decision": "rejected", "feedback": RAW}}, st)
    assert_plain(rejected)
    assert "not applied" in rejected["summary"]


def test_failed_state_and_nonstructured_messages_fail_closed():
    st = {"status": "failed", "status_reason": RAW, "plan": [RAW], "hypotheses": [{"text": RAW}], "history": history()}
    assert_plain(run_display(st))
    for kind in ("agent.message", "approval.requested", "gen_ai.span", "memory.update"):
        assert event_display({"type": kind, "payload": {"text": RAW, "summary": RAW}}, st) is None
    event = {"type": "tool.result", "payload": {"name": "search_logs", "content": RAW}, "event_hash": "original"}
    projected = present_event(event, st)
    assert projected["payload"] == event["payload"] and projected["event_hash"] == "original"
    assert "operator" not in event


@pytest.mark.parametrize("decision", ["approve", "reject"])
def test_http_reload_and_sse_share_plain_views_and_preserve_audit(tmp_path, decision):
    settings = Settings(db_path=str(tmp_path / "display.db"), tool_backoff_s=0.01)
    app = create_app(settings, llm=ScriptedPolicy(delay_s=0))
    with TestClient(app) as client:
        rid = client.post("/api/runs", json={"scenario_id": "db-pool-regression"}).json()["run_id"]

        def wait(status):
            for _ in range(500):
                state = client.get(f"/api/runs/{rid}").json()
                if state["status"] == status:
                    return state
                time.sleep(0.01)
            raise AssertionError(f"Did not reach {status}")

        state = wait("awaiting_approval")
        assert "DB_POOL_SIZE" in state["pending"]["args"]["reason"]
        assert_plain(state["pending"]["operator"])
        assert_plain(state["operator"])
        assert client.get(f"/api/runs/{rid}").json()["pending"]["operator"] == state["pending"]["operator"]
        body = {"args": {"reason": RAW, "to_version": "v2.13.1"}} if decision == "approve" else {"feedback": RAW}
        assert client.post(f"/api/runs/{rid}/{decision}", json=body).status_code == 200
        state = wait("completed")
        assert_plain(state["operator"])
        events = client.get(f"/api/runs/{rid}/events").json()
        for event in events:
            assert_plain(event["operator"])
        response = client.get(f"/api/runs/{rid}/stream")
        frames = [json.loads(line[6:]) for line in response.text.splitlines() if line.startswith("data: ")]
        streamed = [frame for frame in frames if "seq" in frame]
        assert [e["operator"] for e in streamed] == [e["operator"] for e in events]
        originals = app.state.runtime.store.events_since(rid)
        assert [e["payload"] for e in events] == [e["payload"] for e in originals]
        assert [e["event_hash"] for e in events] == [e["event_hash"] for e in originals]
        assert client.get(f"/api/runs/{rid}/events/verify").json()["ok"] is True
        if decision == "approve":
            assert any(f["value"] == "v2.13.1" for f in state["operator"]["report"]["fields"])
        else:
            assert app.state.runtime.get(rid)["env"]["applied"] == {}
