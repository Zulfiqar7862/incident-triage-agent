"""End-to-end and unit tests. They drive the real runtime with the offline
scripted policy, so they need no API key and run in a few seconds."""
from __future__ import annotations

import asyncio
import contextlib
import time

import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.context import build_context, truncate_output
from app.llm import LLMResponse, LLMTransientError, ToolCall
from app.main import create_app
from app.runtime import RunStateError, Runtime
from app.scripted import ScriptedPolicy
from app.store import Store


def make(tmp_path, delay: float = 0.0, **overrides):
    settings = Settings(db_path=str(tmp_path / "test.db"), tool_backoff_s=0.01, llm_backoff_s=0.01, **overrides)
    store = Store(settings.db_path)
    return settings, store, Runtime(store, ScriptedPolicy(delay_s=delay), settings)


async def wait_for(store: Store, run_id: str, statuses: set[str], timeout: float = 10.0) -> dict:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        st = store.load(run_id)
        if st["status"] in statuses:
            return st
        await asyncio.sleep(0.01)
    raise AssertionError(f"timed out waiting for {statuses}; status={st['status']} reason={st['status_reason']}")


def event_types(store: Store, run_id: str) -> list[str]:
    return [e["type"] for e in store.events_since(run_id, 0, limit=10_000)]


# ---- end-to-end scenarios -----------------------------------------------------------------
def test_bad_deploy_is_rolled_back_after_approval(tmp_path):
    async def go():
        _, store, rt = make(tmp_path)
        rid = rt.create_run("db-pool-regression")["run_id"]
        st = await wait_for(store, rid, {"awaiting_approval"})
        assert st["pending"]["tool"] == "rollback_deploy"
        assert st["pending"]["args"]["to_version"] == "v2.13.2"
        assert st["env"]["applied"] == {}  # nothing touched production before approval

        rt.approve(rid)
        st = await wait_for(store, rid, {"completed"})
        assert st["result"]["resolved"] and st["result"]["sim_resolved"]
        assert "pool" in st["result"]["root_cause"].lower()
        types = event_types(store, rid)
        assert "tool.retry" in types  # the flaky log backend was retried, not surfaced as a failure
        assert "memory.saved" in types
    asyncio.run(go())


def test_agent_follows_errors_upstream_past_a_red_herring_deploy(tmp_path):
    async def go():
        _, store, rt = make(tmp_path)
        rid = rt.create_run("upstream-oom")["run_id"]
        st = await wait_for(store, rid, {"awaiting_approval"})
        assert (st["pending"]["tool"], st["pending"]["args"]["service"]) == ("restart_service", "fraud-check")
        assert {h["id"]: h["status"] for h in st["hypotheses"]} == {"H1": "rejected", "H2": "confirmed"}
        rt.approve(rid)
        st = await wait_for(store, rid, {"completed"})
        assert st["result"]["sim_resolved"]
    asyncio.run(go())


def test_rejection_is_fed_back_and_nothing_is_executed(tmp_path):
    async def go():
        _, store, rt = make(tmp_path)
        rid = rt.create_run("db-pool-regression")["run_id"]
        await wait_for(store, rid, {"awaiting_approval"})
        rt.reject(rid, "Change freeze in effect; page the checkout team instead.")
        st = await wait_for(store, rid, {"completed"})
        assert st["env"]["applied"] == {}
        assert st["result"]["resolved"] is False
        tool_msgs = [m["content"] for m in st["history"] if m["role"] == "tool"]
        assert any("REJECTED" in c and "Change freeze" in c for c in tool_msgs)
    asyncio.run(go())


def test_operator_can_edit_arguments_before_approving(tmp_path):
    async def go():
        _, store, rt = make(tmp_path)
        rid = rt.create_run("db-pool-regression")["run_id"]
        await wait_for(store, rid, {"awaiting_approval"})
        rt.approve(rid, {"to_version": "v2.13.1"})
        st = await wait_for(store, rid, {"completed"})
        applied = list(st["env"]["applied"].values())
        assert applied[0]["args"]["to_version"] == "v2.13.1"
        assert st["operator_log"][-1]["edited"] is True
    asyncio.run(go())


# ---- durability ------------------------------------------------------------------------------
def test_run_survives_a_crash_and_resumes_from_checkpoint(tmp_path):
    async def go():
        settings, store, rt = make(tmp_path, delay=0.05)
        rid = rt.create_run("db-pool-regression")["run_id"]
        while store.load(rid)["step"] < 2:
            await asyncio.sleep(0.01)
        task = rt._tasks[rid]
        task.cancel()  # simulate the process dying mid-step
        with contextlib.suppress(asyncio.CancelledError):
            await task
        before = store.load(rid)
        assert before["status"] == "running"

        rt2 = Runtime(store, ScriptedPolicy(delay_s=0), settings)  # "new process"
        assert rt2.recover() == 1
        assert store.load(rid)["status"] == "interrupted"
        rt2.resume(rid)
        st = await wait_for(store, rid, {"awaiting_approval"})
        assert st["step"] > before["step"]
        assert st["actions"][: len(before["actions"])] == before["actions"]  # earlier work kept, not redone
        rt2.approve(rid)
        st = await wait_for(store, rid, {"completed"})
        assert st["result"]["sim_resolved"]
    asyncio.run(go())


def test_approval_survives_restart_and_is_idempotent(tmp_path):
    async def go():
        settings, store, rt = make(tmp_path)
        rid = rt.create_run("db-pool-regression")["run_id"]
        await wait_for(store, rid, {"awaiting_approval"})
        rt2 = Runtime(store, ScriptedPolicy(delay_s=0), settings)
        rt2.recover()
        assert store.load(rid)["status"] == "awaiting_approval"  # a pending human decision is not lost
        rt2.approve(rid)
        with pytest.raises(RunStateError):
            rt2.approve(rid)  # double-click / replay does not apply the change twice
        st = await wait_for(store, rid, {"completed"})
        assert len(st["env"]["applied"]) == 1
    asyncio.run(go())


def test_pause_and_resume(tmp_path):
    async def go():
        _, store, rt = make(tmp_path, delay=0.05)
        rid = rt.create_run("upstream-oom")["run_id"]
        await asyncio.sleep(0.02)
        rt.pause(rid)
        st = await wait_for(store, rid, {"paused"})
        rt.resume(rid)
        await wait_for(store, rid, {"awaiting_approval"})
        assert st["step"] >= 1
    asyncio.run(go())


def test_step_budget_stops_runaway_loops(tmp_path):
    async def go():
        _, store, rt = make(tmp_path, max_steps=2)
        rid = rt.create_run("db-pool-regression")["run_id"]
        st = await wait_for(store, rid, {"needs_attention"})
        assert st["step"] == 2 and "Step budget" in st["status_reason"]
        rt.resume(rid)  # grants 10 more steps
        await wait_for(store, rid, {"awaiting_approval"})
    asyncio.run(go())


# ---- guardrails with a fake model ---------------------------------------------------------------
class FakeLLM:
    provider, model = "fake", "fake"

    def __init__(self, responses):
        self.responses = list(responses)

    async def complete(self, system, messages, tools, state=None):
        r = self.responses.pop(0)
        if isinstance(r, Exception):
            raise r
        return r


def test_low_confidence_write_is_bounced_back_to_the_agent(tmp_path):
    async def go():
        settings = Settings(db_path=str(tmp_path / "t.db"), llm_backoff_s=0.01)
        store = Store(settings.db_path)
        llm = FakeLLM([
            LLMResponse("guess", [ToolCall("c1", "restart_service", {"service": "orders-db", "reason": "hunch", "confidence": 0.2})]),
            LLMTransientError("HTTP 529 overloaded"),  # retried with backoff
            LLMResponse("ok", [ToolCall("c2", "finish", {"summary": "s", "root_cause": "unknown", "resolved": False})]),
        ])
        rt = Runtime(store, llm, settings)
        rid = rt.create_run("db-pool-regression")["run_id"]
        st = await wait_for(store, rid, {"completed"})
        assert st["env"]["applied"] == {}
        types = event_types(store, rid)
        assert "policy.blocked" in types and "approval.requested" not in types and "llm.retry" in types
    asyncio.run(go())


def test_invalid_tool_arguments_are_returned_as_errors(tmp_path):
    async def go():
        settings = Settings(db_path=str(tmp_path / "t.db"))
        store = Store(settings.db_path)
        llm = FakeLLM([
            LLMResponse("", [ToolCall("c1", "query_metrics", {"service": "checkout-service"}), ToolCall("c2", "no_such_tool", {})]),
            LLMResponse("", [ToolCall("c3", "finish", {"summary": "s", "root_cause": "r", "resolved": False})]),
        ])
        rt = Runtime(store, llm, settings)
        rid = rt.create_run("db-pool-regression")["run_id"]
        st = await wait_for(store, rid, {"completed"})
        errs = [m["content"] for m in st["history"] if m["role"] == "tool" and m["is_error"]]
        assert any("metric: Field required" in e for e in errs) and any("Unknown tool" in e for e in errs)
    asyncio.run(go())


# ---- context engineering ---------------------------------------------------------------------------
def test_truncation_keeps_head_and_tail():
    text = "\n".join(f"line {i:03d} " + "x" * 60 for i in range(300))
    out, info = truncate_output(text, 2000)
    assert len(out) < 2300 and info["omitted_chars"] > 0
    assert out.startswith("line 000") and out.rstrip().endswith("x") and "line 299" in out
    assert "truncated" in out


def test_compaction_respects_budget_and_never_splits_tool_pairs(tmp_path):
    async def go():
        settings, store, rt = make(tmp_path)
        rid = rt.create_run("upstream-oom")["run_id"]
        await wait_for(store, rid, {"awaiting_approval"})
        st = store.load(rid)
        tight = Settings(context_budget_tokens=3500, keep_recent_groups=2)
        messages, stats = build_context(st, tight)
        assert stats["dropped_groups"] > 0 and stats["shrunk_messages"] >= 0
        assert messages[0]["role"] == "user" and "<working_memory>" in messages[0]["content"]
        assert "compacted out" in messages[0]["content"]
        seen = set()
        for m in messages:
            if m["role"] == "assistant":
                seen |= {c["id"] for c in m["tool_calls"]}
            if m["role"] == "tool":
                assert m["tool_call_id"] in seen  # every result follows its call
        assert all(a["tool"] for a in st["actions"])  # the action log still records every step
    asyncio.run(go())


def test_long_term_memory_is_recalled_on_the_next_run(tmp_path):
    async def go():
        _, store, rt = make(tmp_path)
        rid = rt.create_run("db-pool-regression")["run_id"]
        await wait_for(store, rid, {"awaiting_approval"})
        rt.approve(rid)
        await wait_for(store, rid, {"completed"})
        st2 = rt.create_run("db-pool-regression")
        assert st2["recalled_memories"] and "pool" in st2["recalled_memories"][0]["root_cause"].lower()
        messages, _ = build_context(store.load(st2["run_id"]), Settings())
        assert "Past incidents for this service" in messages[0]["content"]
    asyncio.run(go())


# ---- HTTP API ---------------------------------------------------------------------------------------
def test_http_api_round_trip(tmp_path):
    settings = Settings(db_path=str(tmp_path / "api.db"), tool_backoff_s=0.01)
    app = create_app(settings, llm=ScriptedPolicy(delay_s=0))
    with TestClient(app) as client:
        assert client.get("/api/health").json()["llm"]["provider"] == "scripted"
        assert len(client.get("/api/tools").json()) == 12
        rid = client.post("/api/runs", json={"scenario_id": "upstream-oom"}).json()["run_id"]
        for _ in range(300):
            st = client.get(f"/api/runs/{rid}").json()
            if st["status"] == "awaiting_approval":
                break
            time.sleep(0.01)
        assert st["status"] == "awaiting_approval"
        assert client.get(f"/api/runs/{rid}/context").json()["stats"]["total_tokens"] > 0
        assert client.post(f"/api/runs/{rid}/approve", json={"args": {"confidence": 5}}).status_code == 422
        assert client.post(f"/api/runs/{rid}/approve", json={}).status_code == 200
        for _ in range(300):
            st = client.get(f"/api/runs/{rid}").json()
            if st["status"] == "completed":
                break
            time.sleep(0.01)
        assert st["result"]["resolved"]
        assert client.post(f"/api/runs/{rid}/approve", json={}).status_code == 409
        assert client.get("/api/runs/nope").status_code == 404
        assert client.post("/api/runs", json={"scenario_id": "../etc/passwd"}).status_code == 404
        assert len(client.get(f"/api/runs/{rid}/events").json()) > 10


def test_mid_approval_crash_does_not_duplicate_tool_result(tmp_path):
    """Crash after recording the tool result but before clearing pending must not double-append."""
    async def go():
        from app.tools import TOOLS
        from app.llm import ToolCall

        settings, store, rt = make(tmp_path)
        rid = rt.create_run("db-pool-regression")["run_id"]
        await wait_for(store, rid, {"awaiting_approval"})
        st = store.load(rid)
        p = st["pending"]
        args = TOOLS[p["tool"]].parse(p["args"])
        final = args.model_dump()
        p["executing"], p["final_args"] = True, final
        content = TOOLS[p["tool"]].handler(rt._cluster(st), args, p["tool_call_id"])
        rt._record(st, p["step"], ToolCall(p["tool_call_id"], p["tool"], final),
                   f"Operator APPROVED this action.\nResult: {content}", False, {})
        store.save(st)  # pending still set — crash window

        rt2 = Runtime(store, ScriptedPolicy(delay_s=0), settings)
        assert rt2.recover() == 1
        assert store.load(rid)["status"] == "interrupted"
        rt2.resume(rid)  # completes idempotent approval without a second human click
        st = await wait_for(store, rid, {"completed"})
        n = sum(1 for m in st["history"] if m.get("role") == "tool" and m.get("tool_call_id") == p["tool_call_id"])
        assert n == 1
        assert len(st["env"]["applied"]) == 1
        assert st["result"]["sim_resolved"]
    asyncio.run(go())
