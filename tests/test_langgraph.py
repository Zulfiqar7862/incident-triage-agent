"""LangGraph topology and interrupt/resume smoke tests."""
from __future__ import annotations

import asyncio

from app.agent.graph import build_agent_graph, graph_mermaid
from app.config import Settings
from app.runtime import Runtime
from app.scripted import ScriptedPolicy
from app.store import Store


def test_graph_mermaid_mentions_gates():
    text = graph_mermaid()
    assert "approval" in text and "interrupt" in text.lower() or "approval" in text


def test_compiled_graph_node_names():
    g = build_agent_graph(True)
    names = set(g.get_graph().nodes)
    for need in ("prepare", "act", "approval", "input"):
        assert need in names


def test_interrupt_resume_reject(tmp_path):
    async def go():
        settings = Settings(db_path=str(tmp_path / "lg.db"), tool_backoff_s=0.01)
        store = Store(settings.db_path)
        rt = Runtime(store, ScriptedPolicy(delay_s=0), settings)
        rid = rt.create_run("db-pool-regression")["run_id"]
        for _ in range(500):
            st = store.load(rid)
            if st["status"] == "awaiting_approval":
                break
            await asyncio.sleep(0.01)
        else:
            raise AssertionError(st["status"])
        rt.reject(rid, "freeze")
        for _ in range(500):
            st = store.load(rid)
            if st["status"] == "completed":
                break
            await asyncio.sleep(0.01)
        assert st["env"]["applied"] == {}
        assert any("REJECTED" in (m.get("content") or "") for m in st["history"] if m.get("role") == "tool")

    asyncio.run(go())
