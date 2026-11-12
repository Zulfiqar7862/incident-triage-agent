"""Facade over the per-step use cases the LangGraph nodes call (implements ``AgentStepsPort``).

Each method delegates to one collaborator: the Store roles, ``LLMGateway``,
``ToolCallDispatcher``, ``GateResolver``, ``RunControls``. The nodes stay thin
and depend on the Protocol only.
"""

from __future__ import annotations

from collections.abc import Callable

from app.application.context import build_context
from app.application.events import RunEventRecorder
from app.application.exceptions import NotFound
from app.application.gate_resolver import GateResolver
from app.application.llm_gateway import LLMGateway
from app.application.ports import DispatchResult
from app.application.run_controls import CONTROL_STATUS, RunControls
from app.application.tool_dispatch import ToolCallDispatcher
from app.core.config import Settings
from app.domain.budget import budget_crossings, exhausted_budget
from app.domain.lifecycle import NUDGE
from app.domain.llm import LLMResponse, ToolCall
from app.domain.memory import make_memory
from app.domain.ports import ClusterPort, IncidentMemory, OperatorInbox, RunRepository


class AgentSteps:
    """What one agent step may do. Constructed once by the composition root."""

    def __init__(
        self,
        *,
        runs: RunRepository,
        inbox: OperatorInbox,
        memory: IncidentMemory,
        settings: Settings,
        events: RunEventRecorder,
        llm: LLMGateway,
        dispatcher: ToolCallDispatcher,
        gates: GateResolver,
        controls: RunControls,
        cluster_for: Callable[[dict], ClusterPort],
    ) -> None:
        self._runs = runs
        self._inbox = inbox
        self._memory = memory
        self._settings = settings
        self._events = events
        self._llm = llm
        self._dispatcher = dispatcher
        self._gates = gates
        self._controls = controls
        self._cluster_for = cluster_for

    # ---- state ----------------------------------------------------------------------------
    def load(self, run_id: str) -> dict:
        """Latest Store checkpoint, so operator edits and inbox items are visible."""
        st = self._runs.load(run_id)
        if st is None:
            raise NotFound(f"Run '{run_id}' not found")
        return st

    def save(self, st: dict) -> None:
        self._runs.save(st)

    def set_status(self, st: dict, status: str, reason: str | None = None) -> None:
        self._events.set_status(st, status, reason)

    # ---- step boundary (prepare) ------------------------------------------------------------
    def take_control(self, run_id: str) -> str | None:
        return self._controls.take(run_id)

    def apply_control(self, st: dict, action: str) -> bool:
        """Apply a pause / cancel request. Returns False for an unknown action."""
        if action not in CONTROL_STATUS:
            return False
        status, reason = CONTROL_STATUS[action]
        self.set_status(st, status, reason)
        return True

    def stop_if_over_budget(self, st: dict) -> bool:
        """Park (or, with ``BUDGET_HARD_STOP``, cancel) a run whose ceiling is used up."""
        hard = self._settings.budget_hard_stop
        reason = exhausted_budget(st, default_cost_cap=self._settings.max_run_cost_usd, hard_stop=hard)
        if reason is None:
            return False
        if hard:
            self.set_status(st, "cancelled", reason + " (hard budget stop).")
        else:
            self.set_status(st, "needs_attention", reason)
        return True

    def maybe_budget_alert(self, st: dict) -> None:
        """Emit a one-shot ``budget.alert`` as usage crosses the configured ratio of each ceiling."""
        ratio = self._settings.budget_alert_ratio
        alerts = set(st.get("budget_alerts") or [])
        crossings = budget_crossings(
            st, ratio=ratio, default_cost_cap=self._settings.max_run_cost_usd, already_alerted=alerts
        )
        for c in crossings:
            alerts.add(c.budget)
            st["budget_alerts"] = sorted(alerts)
            self._events.emit(
                st,
                "budget.alert",
                {
                    "budget": c.budget,
                    "used": c.used,
                    "limit": c.limit,
                    "ratio": ratio,
                    "message": f"{c.budget} usage is at {c.used}/{c.limit} (>= {int(ratio * 100)}% of budget)",
                },
            )

    # ---- model turn (act) -------------------------------------------------------------------
    def drain_inbox(self, st: dict, step: int) -> list[int]:
        """Move queued operator messages into the transcript; returns ids to ack after saving."""
        items = self._inbox.peek_inbox(st["run_id"])
        for item in items:
            st["history"].append({"role": "user", "content": f"[Operator message] {item['text']}", "step": step})
            st["operator_log"].append({"step": step, "decision": "message", "text": item["text"], "at": item["ts"]})
        return [item["id"] for item in items]

    def ack_inbox(self, acks: list[int]) -> None:
        self._inbox.ack_inbox(acks)

    def build_messages(self, st: dict) -> list[dict]:
        """Layered prompt for this turn; emits ``context.compacted`` when older turns were dropped."""
        messages, stats = build_context(st, self._settings)
        st["last_context"] = stats
        if stats["dropped_groups"] > st["compacted_groups"]:
            self._events.emit(
                st, "context.compacted", {"dropped_groups": stats["dropped_groups"], "budget": stats["budget"]}
            )
        st["compacted_groups"] = stats["dropped_groups"]
        return messages

    async def call_llm(self, st: dict, messages: list[dict]) -> LLMResponse:
        return await self._llm.complete(st, messages, st["last_context"])

    def record_assistant(self, st: dict, resp: LLMResponse, step: int) -> None:
        """Append the model's turn to the transcript and publish any prose as ``agent.message``."""
        assistant: dict = {
            "role": "assistant",
            "text": resp.text,
            "step": step,
            "tool_calls": [{"id": c.id, "name": c.name, "args": c.args} for c in resp.tool_calls],
        }
        if resp.raw:
            assistant["raw"] = resp.raw
        st["history"].append(assistant)
        if resp.text:
            self._events.emit(st, "agent.message", {"text": resp.text})

    def nudge(self, st: dict, step: int) -> str:
        """The model replied without a tool call: nudge it, or park the run after three misses."""
        st["nudges"] += 1
        if st["nudges"] > 2:
            self.set_status(st, "needs_attention", "The agent stopped calling tools. Send guidance and resume.")
            return "stop"
        st["history"].append({"role": "user", "content": NUDGE, "step": step})
        return "continue"

    async def dispatch(self, st: dict, calls: list[ToolCall], step: int) -> DispatchResult:
        st["nudges"] = 0
        return await self._dispatcher.dispatch(st, calls, step)

    def conclude(self, st: dict, result: DispatchResult) -> str:
        """Turn a dispatch result into the next graph route: stop, approval, input, or continue."""
        if result.loop_stop_reason:
            self.set_status(st, "needs_attention", result.loop_stop_reason)
            return "stop"
        if result.finish is not None:
            self._finish(st, result.finish)
            return "stop"
        if result.pending is not None:
            # Status flips to awaiting_* only after the interrupt is checkpointed (GraphRunner).
            st["pending"] = result.pending
            return "approval" if result.pending["kind"] == "approval" else "input"
        return "continue"

    def _finish(self, st: dict, result: dict) -> None:
        result["sim_resolved"] = self._cluster_for(st).resolved()  # simulator ground truth, for evaluation only
        st["result"] = result
        if result["resolved"]:
            mem = make_memory(st, result)
            self._memory.add_memory(st["service"], st["run_id"], mem)
            self._events.emit(st, "memory.saved", {"memory": mem})
        self._events.emit(st, "run.finished", {"result": result, "usage": st["usage"]})
        self.set_status(
            st,
            "completed",
            "The agent reports the incident resolved"
            if result["resolved"]
            else "The agent finished without resolving the incident",
        )

    # ---- human gates ----------------------------------------------------------------------
    def resolve_approval(self, st: dict, pending: dict | None, decision: dict | None) -> None:
        self._gates.resolve_approval(st, pending, decision)

    def resolve_answer(self, st: dict, pending: dict | None, decision: dict | None) -> None:
        self._gates.resolve_answer(st, pending, decision)
