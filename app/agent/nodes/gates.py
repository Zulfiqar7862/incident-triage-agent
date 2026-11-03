"""Human-in-the-loop gate nodes using LangGraph interrupt() + Command(resume=...)."""
from __future__ import annotations

import json
import time
from typing import Any

from langchain_core.runnables import RunnableConfig
from langgraph.types import interrupt

from app.llm import ToolCall
from app.tools import TOOLS, ToolArgsError


def _fmt(out) -> str:
    return out if isinstance(out, str) else json.dumps(out, indent=1, ensure_ascii=False)


async def approval_node(state: dict, config: RunnableConfig) -> dict[str, Any]:
    from app.agent.deps import runtime_from
    from app.mock_env import ToolError

    rt = runtime_from(config)
    st = rt.get(state["run_id"])
    pending = st.get("pending") or state.get("pending")
    if not pending or pending.get("kind") != "approval":
        st["route"] = "continue"
        return st

    # Pause first. Runtime._drive flips Store status to awaiting_approval only
    # after ainvoke returns, so the interrupt checkpoint is already durable.
    decision = interrupt(pending)

    st = rt.get(state["run_id"])
    p = st.get("pending") or pending
    if not p or p.get("kind") != "approval":
        st["route"] = "continue"
        rt.store.save(st)
        return st

    if rt._tool_result_recorded(st, p["tool_call_id"]):
        st["pending"] = None
        st["route"] = "continue"
        rt.store.save(st)
        return st

    kind = (decision or {}).get("decision", "approved")
    actor = (decision or {}).get("actor", "operator")

    if kind == "rejected":
        feedback = (decision.get("feedback") or "").strip()
        st["operator_log"].append(
            {
                "step": p["step"],
                "decision": "rejected",
                "tool": p["tool"],
                "feedback": feedback,
                "actor": actor,
                "at": time.time(),
            }
        )
        rt._emit(
            st,
            "approval.decided",
            {"id": p["tool_call_id"], "decision": "rejected", "tool": p["tool"], "feedback": feedback, "actor": actor},
        )
        rt._record(
            st,
            p["step"],
            ToolCall(p["tool_call_id"], p["tool"], p["args"]),
            f"Operator REJECTED this action; it was NOT executed. Feedback: {feedback or '(none given)'}",
            False,
            {},
        )
        st["pending"] = None
        st["route"] = "continue"
        rt.store.save(st)
        try:
            from app.observability.metrics import record_approval

            record_approval("rejected")
        except Exception:  # noqa: BLE001
            pass
        return st

    spec = TOOLS[p["tool"]]
    edited_args = decision.get("args")
    base_args = p.get("final_args") or p["args"]
    try:
        args = spec.parse({**base_args, **(edited_args or {})})
    except ToolArgsError as e:
        rt._record(
            st,
            p["step"],
            ToolCall(p["tool_call_id"], p["tool"], base_args),
            f"Edited arguments are invalid: {e}",
            True,
            {},
        )
        st["pending"] = None
        st["route"] = "continue"
        rt.store.save(st)
        return st

    final = args.model_dump()
    edited = final != p["args"]
    p["executing"], p["final_args"] = True, final
    st["pending"] = p
    rt.store.save(st)

    try:
        content, is_error = _fmt(spec.handler(rt._cluster(st), args, p["tool_call_id"])), False
    except ToolError as e:
        content, is_error = f"Execution failed: {e}", True

    if rt._tool_result_recorded(st, p["tool_call_id"]):
        st["pending"] = None
        st["route"] = "continue"
        rt.store.save(st)
        return st

    header = "Operator APPROVED this action" + (
        f" after editing the arguments to {json.dumps(final)}" if edited else ""
    ) + "."
    if actor == "system-resume":
        header = "Resumed an interrupted approval; replaying the idempotent production change."
    st["operator_log"].append(
        {
            "step": p["step"],
            "decision": "approved",
            "tool": p["tool"],
            "args": final,
            "edited": edited,
            "actor": actor,
            "at": time.time(),
        }
    )
    rt._emit(
        st,
        "approval.decided",
        {
            "id": p["tool_call_id"],
            "decision": "approved",
            "tool": p["tool"],
            "args": final,
            "edited": edited,
            "actor": actor,
        },
    )
    rt._record(
        st,
        p["step"],
        ToolCall(p["tool_call_id"], p["tool"], final),
        f"{header}\nResult: {content}",
        is_error,
        {},
    )
    st["pending"] = None
    st["route"] = "continue"
    rt.store.save(st)
    try:
        from app.observability.metrics import record_approval

        record_approval("approved")
    except Exception:  # noqa: BLE001
        pass
    return st


async def input_node(state: dict, config: RunnableConfig) -> dict[str, Any]:
    from app.agent.deps import runtime_from

    rt = runtime_from(config)
    st = rt.get(state["run_id"])
    pending = st.get("pending") or state.get("pending")
    if not pending or pending.get("kind") != "input":
        st["route"] = "continue"
        return st

    decision = interrupt(pending)
    st = rt.get(state["run_id"])
    p = st.get("pending") or pending
    if not p or p.get("kind") != "input":
        st["route"] = "continue"
        rt.store.save(st)
        return st

    text = (decision or {}).get("text") or ""
    actor = (decision or {}).get("actor", "operator")
    st["operator_log"].append({"step": p["step"], "decision": "message", "text": text, "at": time.time()})
    rt._emit(st, "operator.message", {"text": text, "answering": p["question"], "actor": actor})
    rt._record(
        st,
        p["step"],
        ToolCall(p["tool_call_id"], "ask_operator", p["args"]),
        f"Operator answered: {text}",
        False,
        {},
    )
    st["pending"] = None
    st["route"] = "continue"
    rt.store.save(st)
    return st
