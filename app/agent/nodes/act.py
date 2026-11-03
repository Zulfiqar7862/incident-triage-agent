"""LLM + tool dispatch node (reads/memory/finish). Gates route to interrupt nodes."""
from __future__ import annotations

import asyncio
import time
from typing import Any

from langchain_core.runnables import RunnableConfig

from app.context import build_context
from app.guards import LoopGuard
from app.llm import ToolCall
from app.tools import TOOLS, ToolArgsError

NUDGE = (
    "You did not call a tool. Continue the investigation with a tool call, "
    "use ask_operator if you are blocked, or call finish if you are done."
)


async def act_node(state: dict, config: RunnableConfig) -> dict[str, Any]:
    from app.agent.deps import runtime_from

    rt = runtime_from(config)
    st = rt.get(state["run_id"])  # fresh from Store
    st["step"] += 1
    step = st["step"]

    inbox = rt.store.peek_inbox(st["run_id"])
    for item in inbox:
        st["history"].append({"role": "user", "content": f"[Operator message] {item['text']}", "step": step})
        st["operator_log"].append({"step": step, "decision": "message", "text": item["text"], "at": item["ts"]})
    acks = [i["id"] for i in inbox]
    st["inbox_acks"] = acks

    messages, stats = build_context(st, rt.settings)
    st["last_context"] = stats
    if stats["dropped_groups"] > st["compacted_groups"]:
        rt._emit(st, "context.compacted", {"dropped_groups": stats["dropped_groups"], "budget": stats["budget"]})
    st["compacted_groups"] = stats["dropped_groups"]

    t0 = time.perf_counter()
    resp = await rt._call_llm(st, messages)
    ms = int((time.perf_counter() - t0) * 1000)
    u = st["usage"]
    cost = (
        resp.input_tokens * rt.settings.cost_in_per_mtok
        + resp.output_tokens * rt.settings.cost_out_per_mtok
    ) / 1e6
    u["llm_calls"] += 1
    u["input_tokens"] += resp.input_tokens
    u["output_tokens"] += resp.output_tokens
    u["cost_usd"] = round(u["cost_usd"] + cost, 6)
    u["llm_ms"] += ms
    rt._emit(
        st,
        "llm.call",
        {
            "model": resp.model,
            "input_tokens": resp.input_tokens,
            "output_tokens": resp.output_tokens,
            "latency_ms": ms,
            "cost_usd": round(cost, 6),
            "context": stats,
            "tool_calls": len(resp.tool_calls),
        },
    )
    try:
        from app.observability.metrics import record_llm_call

        record_llm_call(resp.model, resp.input_tokens, resp.output_tokens, cost, ms / 1000.0)
    except Exception:  # noqa: BLE001
        pass

    calls = resp.tool_calls
    assistant = {
        "role": "assistant",
        "text": resp.text,
        "step": step,
        "tool_calls": [{"id": c.id, "name": c.name, "args": c.args} for c in calls],
    }
    if resp.raw:
        assistant["raw"] = resp.raw
    st["history"].append(assistant)
    if resp.text:
        rt._emit(st, "agent.message", {"text": resp.text})

    if not calls:
        st["nudges"] += 1
        if st["nudges"] > 2:
            rt._set_status(st, "needs_attention", "The agent stopped calling tools. Send guidance and resume.")
            st["route"] = "stop"
            rt.store.ack_inbox(acks)
            return st
        st["history"].append({"role": "user", "content": NUDGE, "step": step})
        st["route"] = "continue"
        rt.store.save(st)
        rt.store.ack_inbox(acks)
        return st
    st["nudges"] = 0

    for c in calls:
        spec = TOOLS.get(c.name)
        rt._emit(st, "tool.call", {"id": c.id, "name": c.name, "args": c.args, "kind": spec.kind if spec else "unknown"})

    results: dict[str, tuple] = {}
    reads: list[tuple[ToolCall, Any]] = []
    gate: dict | None = None
    finish: ToolCall | None = None
    for c in calls:
        spec = TOOLS.get(c.name)
        if spec is None:
            results[c.id] = (f"Unknown tool '{c.name}'. Available tools: {', '.join(TOOLS)}", True, {})
        elif spec.kind == "read":
            reads.append((c, spec))
        elif c.name == "finish":
            finish = c
        elif c.name == "update_working_memory":
            results[c.id] = rt._apply_memory(st, c, spec)
        elif gate is not None:
            results[c.id] = (
                "Not executed: only one production change or operator question can be pending at a time. "
                "Re-issue it after the current one is resolved.",
                True,
                {},
            )
        else:
            outcome = rt._gate(st, c, spec, step)
            if isinstance(outcome, tuple):
                results[c.id] = outcome
            else:
                gate = outcome

    if reads:
        outs = await asyncio.gather(*(rt._exec_read(st, c, spec) for c, spec in reads))
        for (c, _), out in zip(reads, outs, strict=True):
            results[c.id] = out

    done = None
    if finish is not None:
        if gate is not None:
            results[finish.id] = ("Not finished: an operator decision is still pending.", True, {})
        else:
            try:
                done = TOOLS["finish"].parse(finish.args)
                results[finish.id] = ("Run finished.", False, {})
            except ToolArgsError as e:
                results[finish.id] = (f"Invalid arguments for finish: {e}", True, {})

    for c in calls:
        if c.id in results:
            rt._record(st, step, c, *results[c.id])

    guard = LoopGuard(rt.settings.max_identical_tool_calls)
    guard.loads(st.get("loop_guard"))
    for c in calls:
        if c.id in results:
            guard.record(c.name, c.args)
    st["loop_guard"] = guard.dumps()
    stop, reason = guard.should_stop()
    if stop and done is None and gate is None:
        rt._set_status(st, "needs_attention", reason)
        st["route"] = "stop"
        rt.store.save(st)
        rt.store.ack_inbox(acks)
        return st

    if done is not None:
        rt._finish(st, done.model_dump())
        st["route"] = "stop"
        rt.store.ack_inbox(acks)
        return st

    if gate is not None:
        # Status flips to awaiting_* inside the gate node, immediately before
        # interrupt(), so waiters cannot observe the gate before it is checkpointed.
        st["pending"] = gate
        st["route"] = "approval" if gate["kind"] == "approval" else "input"
        rt.store.save(st)
        rt.store.ack_inbox(acks)
        return st

    st["route"] = "continue"
    rt.store.save(st)
    rt.store.ack_inbox(acks)
    return st
