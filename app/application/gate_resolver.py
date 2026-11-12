"""Apply an operator's decision to a parked human gate (after LangGraph resumes).

Approve: re-validate (possibly edited) arguments, checkpoint the intent, run the
idempotent production change, record the result. Reject: record that nothing ran.
Answer: hand the operator's reply to the model as the ``ask_operator`` result.
"""

from __future__ import annotations

import json
import time
from collections.abc import Callable, Mapping

from app.application.events import RunEventRecorder
from app.application.ports import TelemetryPort, ToolPresenter
from app.application.tool_executor import ToolExecutor, format_tool_output
from app.application.tools import ToolArgsError, ToolSpec
from app.domain.errors import ToolError
from app.domain.llm import ToolCall
from app.domain.ports import ClusterPort, RunRepository


def tool_result_recorded(st: dict, tool_call_id: str) -> bool:
    """True when the history already holds a result for this call (crash-replay guard)."""
    return any(m.get("role") == "tool" and m.get("tool_call_id") == tool_call_id for m in st.get("history") or [])


class GateResolver:
    """Resolves approvals and operator answers. Graph nodes only call ``interrupt()`` and delegate here."""

    def __init__(
        self,
        *,
        tools: Mapping[str, ToolSpec],
        runs: RunRepository,
        events: RunEventRecorder,
        executor: ToolExecutor,
        cluster_for: Callable[[dict], ClusterPort],
        present_tool: ToolPresenter,
        telemetry: TelemetryPort,
    ) -> None:
        self._tools = tools
        self._runs = runs
        self._events = events
        self._executor = executor
        self._cluster_for = cluster_for
        self._present_tool = present_tool
        self._telemetry = telemetry

    # ---- approvals ------------------------------------------------------------------------
    def resolve_approval(self, st: dict, pending: dict | None, decision: dict | None) -> None:
        """Apply an approve / reject decision. Idempotent if the result was already recorded."""
        if not pending or pending.get("kind") != "approval":
            self._continue(st)
            return
        if tool_result_recorded(st, pending["tool_call_id"]):
            self._close(st)
            return
        decision = decision or {}
        actor = decision.get("actor", "operator")
        if decision.get("decision", "approved") == "rejected":
            self._reject(st, pending, (decision.get("feedback") or "").strip(), actor)
        else:
            self._approve(st, pending, decision.get("args"), actor)

    def _reject(self, st: dict, p: dict, feedback: str, actor: str) -> None:
        self._log_decision(st, p, "rejected", actor, feedback=feedback)
        self._events.emit(
            st,
            "approval.decided",
            {
                "id": p["tool_call_id"],
                "decision": "rejected",
                "tool": p["tool"],
                "feedback": feedback,
                "actor": actor,
                **self._present_tool(p["tool"], p.get("args") or {}),
            },
        )
        self._executor.record(
            st,
            p["step"],
            ToolCall(p["tool_call_id"], p["tool"], p["args"]),
            f"Operator REJECTED this action; it was NOT executed. Feedback: {feedback or '(none given)'}",
            False,
            {},
        )
        self._close(st)
        self._telemetry.approval("rejected")

    def _approve(self, st: dict, p: dict, edited_args: dict | None, actor: str) -> None:
        spec = self._tools[p["tool"]]
        base_args = p.get("final_args") or p["args"]
        try:
            args = spec.parse({**base_args, **(edited_args or {})})
        except ToolArgsError as e:
            call = ToolCall(p["tool_call_id"], p["tool"], base_args)
            self._executor.record(st, p["step"], call, f"Edited arguments are invalid: {e}", True, {})
            self._close(st)
            return

        final = args.model_dump()
        edited = final != p["args"]
        # Checkpoint the intent first: a crash from here on resumes into an idempotent replay.
        p["executing"], p["final_args"] = True, final
        st["pending"] = p
        self._runs.save(st)

        content, is_error = self._execute(st, spec, args, p["tool_call_id"])
        if tool_result_recorded(st, p["tool_call_id"]):
            self._close(st)
            return

        self._log_decision(st, p, "approved", actor, args=final, edited=edited)
        self._events.emit(
            st,
            "approval.decided",
            {
                "id": p["tool_call_id"],
                "decision": "approved",
                "tool": p["tool"],
                "args": final,
                "edited": edited,
                "actor": actor,
                **self._present_tool(p["tool"], final),
            },
        )
        header = _approval_header(final, edited, actor)
        call = ToolCall(p["tool_call_id"], p["tool"], final)
        self._executor.record(st, p["step"], call, f"{header}\nResult: {content}", is_error, {})
        self._close(st)
        self._telemetry.approval("approved")

    def _execute(self, st: dict, spec: ToolSpec, args: object, call_id: str) -> tuple[str, bool]:
        if spec.handler is None:
            return f"{spec.name} has no handler", True
        try:
            return format_tool_output(spec.handler(self._cluster_for(st), args, call_id)), False
        except ToolError as e:
            return f"Execution failed: {e}", True

    # ---- operator questions ---------------------------------------------------------------
    def resolve_answer(self, st: dict, pending: dict | None, decision: dict | None) -> None:
        """Record the operator's reply as the ``ask_operator`` tool result."""
        if not pending or pending.get("kind") != "input":
            self._continue(st)
            return
        decision = decision or {}
        text = decision.get("text") or ""
        actor = decision.get("actor", "operator")
        st["operator_log"].append({"step": pending["step"], "decision": "message", "text": text, "at": time.time()})
        self._events.emit(st, "operator.message", {"text": text, "answering": pending["question"], "actor": actor})
        call = ToolCall(pending["tool_call_id"], "ask_operator", pending["args"])
        self._executor.record(st, pending["step"], call, f"Operator answered: {text}", False, {})
        self._close(st)

    # ---- helpers --------------------------------------------------------------------------
    def _close(self, st: dict) -> None:
        """Clear the gate and continue the loop."""
        st["pending"] = None
        self._continue(st)

    def _continue(self, st: dict) -> None:
        st["route"] = "continue"
        self._runs.save(st)

    @staticmethod
    def _log_decision(st: dict, p: dict, decision: str, actor: str, **extra: object) -> None:
        entry = {"step": p["step"], "decision": decision, "tool": p["tool"], **extra, "actor": actor, "at": time.time()}
        st["operator_log"].append(entry)


def _approval_header(final: dict, edited: bool, actor: str) -> str:
    if actor == "system-resume":
        return "Resumed an interrupted approval; replaying the idempotent production change."
    return (
        "Operator APPROVED this action"
        + (f" after editing the arguments to {json.dumps(final)}" if edited else "")
        + "."
    )
