"""Governance controls: hash-chained audit log, hard budgets, emergency stop, scope, risk labels."""

from __future__ import annotations

import asyncio
import time

from app.core.config import Settings
from app.core.container import build_run_service
from app.infrastructure.llm import LLMResponse, ToolCall
from app.infrastructure.llm.scripted import ScriptedPolicy
from app.infrastructure.persistence.store import Store
from app.main import create_app
from app.presentation.views.decisions import enrich_pending
from app.presentation.views.run_view import present_run
from app.presentation.views.tool_labels import present_tool
from fastapi.testclient import TestClient


async def _wait(store, rid, statuses, timeout=12.0):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        st = store.load(rid)
        if st and st["status"] in statuses:
            return st
        await asyncio.sleep(0.02)
    raise AssertionError(store.load(rid))


def test_event_hash_chain_verifies_and_detects_tamper(tmp_path):
    store = Store(str(tmp_path / "t.db"))
    e1 = store.append_event("r1", "run.created", {"a": 1})
    e2 = store.append_event("r1", "tool.call", {"b": 2})
    assert e1["event_hash"] and e2["prev_hash"] == e1["event_hash"]
    assert store.verify_event_chain("r1")["ok"] is True
    store._exec("UPDATE events SET payload=? WHERE seq=?", ('{"b": 999}', e2["seq"]))
    bad = store.verify_event_chain("r1")
    assert bad["ok"] is False and bad["seq"] == e2["seq"]


def test_present_tool_marks_write_as_high_risk():
    ui = present_tool("rollback_deploy", {"service": "checkout-service", "to_version": "v1"})
    assert ui["risk"] == "high"
    assert ui["title"]
    low = present_tool("query_metrics", {"service": "checkout-service", "metric": "error_rate"})
    assert low["risk"] == "low"
    pending = enrich_pending({"kind": "approval", "tool": "restart_service", "args": {"service": "x"}})
    assert pending["risk"] == "high" and pending["title"]


def test_approval_payload_includes_risk_and_summary(tmp_path):
    async def go():
        settings = Settings(db_path=str(tmp_path / "t.db"), tool_backoff_s=0.01)
        store = Store(settings.db_path)
        rt = build_run_service(store, ScriptedPolicy(delay_s=0), settings)
        rid = rt.create_run("db-pool-regression")["run_id"]
        st = await _wait(store, rid, {"awaiting_approval"})
        p = present_run(rt.queries, st)["pending"]
        assert p["risk"] == "high"
        assert p.get("title") and p.get("summary")
        req = next(e for e in store.events_since(rid, 0, limit=10_000) if e["type"] == "approval.requested")
        assert req["payload"].get("risk") == "high"
        assert store.verify_event_chain(rid)["ok"] is True

    asyncio.run(go())


def test_unknown_service_write_is_blocked_before_approval(tmp_path):
    class Fake:
        provider, model = "fake", "fake"

        def __init__(self):
            self.n = 0

        async def complete(self, system, messages, tools, state=None):
            self.n += 1
            if self.n == 1:
                return LLMResponse(
                    "bad",
                    [
                        ToolCall(
                            "c1",
                            "restart_service",
                            {
                                "service": "not-a-real-service",
                                "reason": "test",
                                "confidence": 0.9,
                            },
                        )
                    ],
                )
            return LLMResponse(
                "done",
                [
                    ToolCall(
                        "c2",
                        "finish",
                        {"summary": "blocked", "root_cause": "bad service", "resolved": False},
                    )
                ],
            )

    async def go():
        settings = Settings(db_path=str(tmp_path / "t.db"), tool_backoff_s=0.01, llm_backoff_s=0.01)
        store = Store(settings.db_path)
        rt = build_run_service(store, Fake(), settings)
        rid = rt.create_run("db-pool-regression")["run_id"]
        await _wait(store, rid, {"completed", "needs_attention", "failed"})
        types = [e["type"] for e in store.events_since(rid, 0, limit=10_000)]
        assert "policy.blocked" in types
        assert "approval.requested" not in types

    asyncio.run(go())


def test_hard_budget_stop_cancels(tmp_path):
    async def go():
        class Looper:
            provider, model = "fake", "fake"
            n = 0

            async def complete(self, system, messages, tools, state=None):
                self.n += 1
                return LLMResponse("x", [ToolCall(f"c{self.n}", "list_services", {})])

        settings = Settings(
            db_path=str(tmp_path / "t.db"),
            max_steps=1,
            budget_hard_stop=True,
            max_identical_tool_calls=99,
            tool_backoff_s=0.01,
        )
        store = Store(settings.db_path)
        rt = build_run_service(store, Looper(), settings)
        rid = rt.create_run("db-pool-regression")["run_id"]
        st = await _wait(store, rid, {"cancelled"})
        assert st["status"] == "cancelled"
        assert "hard budget" in (st.get("status_reason") or "").lower() or "Step budget" in (
            st.get("status_reason") or ""
        )

    asyncio.run(go())


def test_emergency_stop_cancels_active_runs(tmp_path):
    async def go():
        store = Store(str(tmp_path / "e.db"))
        settings = Settings(db_path=str(tmp_path / "e.db"), tool_backoff_s=0.01)
        rt = build_run_service(store, ScriptedPolicy(delay_s=0.05), settings)
        rid = rt.create_run("db-pool-regression")["run_id"]
        await asyncio.sleep(0.02)
        result = rt.emergency_stop()
        assert rid in result["cancelled"]
        st = await _wait(store, rid, {"cancelled"})
        assert st["status"] == "cancelled"

    asyncio.run(go())


def test_emergency_stop_and_verify_http(tmp_path):
    settings = Settings(
        db_path=str(tmp_path / "http.db"),
        llm_provider="scripted",
        require_llm=False,
        scripted_delay_s=0.05,
        tool_backoff_s=0.01,
    )
    app = create_app(settings=settings, llm=ScriptedPolicy(delay_s=0.05))
    with TestClient(app) as client:
        r = client.post("/api/runs", json={"scenario_id": "db-pool-regression"})
        assert r.status_code == 201, r.text
        rid = r.json()["run_id"]
        stop = client.post("/api/emergency-stop")
        assert stop.status_code == 200, stop.text
        body = stop.json()
        assert rid in body["cancelled"]
        # Allow cancel to settle
        deadline = time.monotonic() + 5
        status = None
        while time.monotonic() < deadline:
            status = client.get(f"/api/runs/{rid}").json()["status"]
            if status == "cancelled":
                break
            time.sleep(0.05)
        assert status == "cancelled"
        v = client.get(f"/api/runs/{rid}/events/verify")
        assert v.status_code == 200
        assert v.json()["ok"] is True


def test_public_alert_card_has_no_pcodes(tmp_path):
    from app.application.agent.state import make_run_id, new_run_state
    from app.infrastructure.cluster.mock_cluster import load_scenario

    settings = Settings(db_path=str(tmp_path / "a.db"), tool_backoff_s=0.01)
    store = Store(settings.db_path)
    rt = build_run_service(store, ScriptedPolicy(delay_s=0), settings)
    scenario = load_scenario("db-pool-regression")
    st = new_run_state(make_run_id(), scenario, settings)
    store.create_run(st)
    pub = present_run(rt.queries, st)
    assert "ALRT" not in pub["task"]
    assert "P1" not in pub["task"]
    assert pub["alert"]["severity"] == "Critical"
    assert pub["alert"]["severity_code"] == "P1"  # engineers only
    assert pub["status_label"]
    assert "ALRT" not in pub["alert"]["summary"]
