"""Operational behaviour: auth, audit identity, limits, health, metrics, shutdown."""
from __future__ import annotations

import asyncio
import time

import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app
from app.runtime import Runtime, TooBusy
from app.scripted import ScriptedPolicy
from app.store import Store

TOKEN = "s3cret-token-for-tests-0123"


def client(tmp_path, **overrides) -> TestClient:
    settings = Settings(db_path=str(tmp_path / "p.db"), tool_backoff_s=0.01, **overrides)
    return TestClient(create_app(settings, llm=ScriptedPolicy(delay_s=0)))


def wait_status(c: TestClient, rid: str, want: str, headers=None) -> dict:
    for _ in range(500):
        st = c.get(f"/api/runs/{rid}", headers=headers).json()
        if st["status"] == want:
            return st
        time.sleep(0.01)
    raise AssertionError(st["status"])


def test_api_token_is_required_everywhere_except_probes(tmp_path):
    auth = {"Authorization": f"Bearer {TOKEN}", "X-Operator": "Priya <script>"}
    with client(tmp_path, api_token=TOKEN) as c:
        assert c.get("/healthz").status_code == 200
        assert c.get("/readyz").status_code == 200
        assert c.get("/").status_code == 200  # the UI shell holds no data; it prompts for the token
        assert c.get("/api/runs").status_code == 401
        assert c.get("/api/runs", headers={"Authorization": "Bearer wrong-token-xxxxxxxxx"}).status_code == 401
        assert c.post("/api/runs", json={"scenario_id": "db-pool-regression"}).status_code == 401

        rid = c.post("/api/runs", json={"scenario_id": "db-pool-regression"}, headers=auth).json()["run_id"]
        wait_status(c, rid, "awaiting_approval", auth)
        assert c.post(f"/api/runs/{rid}/approve", json={}).status_code == 401  # no token, no production change
        assert c.post(f"/api/runs/{rid}/approve", json={}, headers=auth).status_code == 200
        st = wait_status(c, rid, "completed", auth)
        assert st["operator_log"][-1]["actor"] == "Priya script"  # identity is recorded, sanitised

        # EventSource can't send headers, so the stream accepts the token as a query parameter.
        assert c.get(f"/api/runs/{rid}/events").status_code == 401
        with c.stream("GET", f"/api/runs/{rid}/stream?token={TOKEN}") as r:
            assert r.status_code == 200
            first = next(r.iter_lines())
            assert first.startswith("retry:")


def test_security_headers_and_metrics(tmp_path):
    with client(tmp_path) as c:
        r = c.get("/healthz")
        assert r.headers["x-content-type-options"] == "nosniff" and r.headers["x-frame-options"] == "DENY"
        rid = c.post("/api/runs", json={"scenario_id": "upstream-oom"}).json()["run_id"]
        wait_status(c, rid, "awaiting_approval")
        m = c.get("/metrics").text
        assert 'agent_runs{status="awaiting_approval"} 1' in m
        assert 'agent_events_total{type="tool.call"}' in m


def test_input_limits_are_enforced(tmp_path):
    with client(tmp_path) as c:
        assert c.post("/api/runs", json={"scenario_id": "x" * 500}).status_code == 422
        rid = c.post("/api/runs", json={"scenario_id": "db-pool-regression"}).json()["run_id"]
        assert c.post(f"/api/runs/{rid}/message", json={"text": "x" * 5000}).status_code == 422


def test_concurrency_limit_returns_429(tmp_path):
    settings = Settings(db_path=str(tmp_path / "c.db"), max_concurrent_runs=1)
    app = create_app(settings, llm=ScriptedPolicy(delay_s=0.5))
    with TestClient(app) as c:
        assert c.post("/api/runs", json={"scenario_id": "db-pool-regression"}).status_code == 201
        r = c.post("/api/runs", json={"scenario_id": "db-pool-regression"})
        assert r.status_code == 429 and r.headers["retry-after"] == "30"


def test_graceful_shutdown_marks_runs_interrupted(tmp_path):
    async def go():
        settings = Settings(db_path=str(tmp_path / "s.db"))
        store = Store(settings.db_path)
        rt = Runtime(store, ScriptedPolicy(delay_s=0.3), settings)
        rid = rt.create_run("db-pool-regression")["run_id"]
        await asyncio.sleep(0.05)
        await rt.shutdown()
        st = store.load(rid)
        assert st["status"] == "interrupted" and "shut down" in st["status_reason"]
        rt2 = Runtime(store, ScriptedPolicy(delay_s=0), settings)
        rt2.resume(rid)
        for _ in range(300):
            if store.load(rid)["status"] == "awaiting_approval":
                return
            await asyncio.sleep(0.01)
        raise AssertionError(store.load(rid)["status"])
    asyncio.run(go())


def test_runtime_rejects_runs_beyond_the_limit(tmp_path):
    async def go():
        settings = Settings(db_path=str(tmp_path / "l.db"), max_concurrent_runs=1)
        rt = Runtime(Store(settings.db_path), ScriptedPolicy(delay_s=0.3), settings)
        rt.create_run("db-pool-regression")
        with pytest.raises(TooBusy):
            rt.create_run("upstream-oom")
        await rt.shutdown()
    asyncio.run(go())
