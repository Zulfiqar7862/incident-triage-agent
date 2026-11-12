"""Run lifecycle use cases: create, pause, resume, cancel, emergency stop, approve,
reject, message, and the LangGraph drive loop.

Lifecycle
    queued -> running -> (awaiting_approval | awaiting_input | paused | needs_attention)
           -> running -> completed | failed | cancelled
    A server restart turns "running" into "interrupted"; resume continues from the
    last LangGraph checkpoint (and the Store checkpoint).

Dependencies arrive through the constructor as ports and factories (Store,
LLM Strategy, cluster adapter factory, checkpointer factory, scenario loader,
pending presenter). This module imports no infrastructure or presentation code;
``app.runtime.Runtime`` wires the default adapters.
"""

from __future__ import annotations

import asyncio
import logging
import threading
from typing import cast

from langgraph.types import Command

from app.agent.graph import build_agent_graph
from app.agent.state import make_run_id, new_run_state
from app.application.events import RunEventRecorder
from app.application.exceptions import ConcurrencyConflict, InvalidInput, NotFound, RunStateError, TooBusy
from app.application.llm_gateway import LLMGateway
from app.application.ports import (
    CheckpointerFactory,
    ClusterFactory,
    PendingPresenter,
    ScenarioCatalog,
    ScenarioLoader,
    ToolOutcome,
)
from app.application.tool_executor import ToolExecutor
from app.application.working_memory import apply_working_memory
from app.application.write_gate import build_gate_or_block
from app.config import Settings
from app.domain.budget import budget_crossings
from app.domain.lifecycle import RESUMABLE, TERMINAL
from app.domain.llm import LLMResponse, ToolCall
from app.domain.memory import make_memory
from app.domain.ports import ClusterPort, LLMPort, RunStorePort
from app.tools import TOOLS, ToolArgsError, ToolSpec, tool_schemas

log = logging.getLogger("agent")


class RunService:
    """Application service for the run lifecycle; implements ``AgentRuntimePort``.

    One instance per process. Collaborators: ``RunEventRecorder`` (audit events),
    ``LLMGateway`` (retrying model calls), ``ToolExecutor`` (read tools + recording).
    """

    def __init__(
        self,
        store: RunStorePort,
        llm: LLMPort,
        settings: Settings,
        *,
        cluster_factory: ClusterFactory,
        checkpointer_factory: CheckpointerFactory,
        scenario_loader: ScenarioLoader,
        present_pending: PendingPresenter = dict,
        scenario_catalog: ScenarioCatalog = list,
    ):
        self.store = store
        self.llm = llm  # LLMPort Strategy (scripted | gemini | anthropic | openai)
        self.settings = settings
        self.tools = tool_schemas()
        self._cluster_factory = cluster_factory
        self._checkpointer_factory = checkpointer_factory
        self._load_scenario = scenario_loader
        self._present_pending = present_pending
        self._scenario_catalog = scenario_catalog
        self.events = RunEventRecorder(store)
        self._llm_gateway = LLMGateway(llm, settings, self.events, self.tools)
        self._tool_executor = ToolExecutor(settings, self.events)
        self._tasks: dict[str, asyncio.Task] = {}
        self._control: dict[str, str] = {}
        self._gate_locks: dict[str, threading.Lock] = {}
        self._gate_locks_mu = threading.Lock()
        self._pending_resume: dict[str, dict] = {}
        self._relaunch: set[str] = set()

    # ---- queries -------------------------------------------------------------------------
    def get(self, run_id: str) -> dict:
        st = self.store.load(run_id)
        if st is None:
            raise NotFound(f"Run '{run_id}' not found")
        return st

    def is_active(self, run_id: str) -> bool:
        t = self._tasks.get(run_id)
        if not (t and not t.done()):
            return False
        st = self.store.load(run_id)
        # Task may still be unwinding after parking on a gate / pause / budget stop.
        if st and st["status"] not in ("running", "queued"):
            return False
        return True

    def _gate_lock(self, run_id: str) -> threading.Lock:
        with self._gate_locks_mu:
            lock = self._gate_locks.get(run_id)
            if lock is None:
                lock = threading.Lock()
                self._gate_locks[run_id] = lock
            return lock

    def tool_result_recorded(self, st: dict, tool_call_id: str) -> bool:
        return any(m.get("role") == "tool" and m.get("tool_call_id") == tool_call_id for m in st.get("history") or [])

    def scenario_alert(self, scenario_id: str) -> dict | None:
        """Alert of a scenario, for checkpoints written before ``alert`` was stored."""
        try:
            return self._load_scenario(scenario_id)["alert"]
        except Exception:  # noqa: BLE001
            return None

    def list_scenarios(self) -> list[dict]:
        return self._scenario_catalog()

    def list_runs(self) -> list[dict]:
        return self.store.list_runs()

    def events_since(self, run_id: str, after: int = 0) -> list[dict]:
        return self.store.events_since(run_id, after)

    def verify_events(self, run_id: str) -> dict:
        self.get(run_id)  # NotFound if missing
        return self.store.verify_event_chain(run_id)

    def health_counts(self) -> tuple[dict[str, int], dict[str, int]]:
        return self.store.status_counts(), self.store.event_counts()

    def ping(self) -> bool:
        return self.store.ping()

    def take_control(self, run_id: str) -> str | None:
        """Pop a pending operator control flag (``pause`` / ``cancel``) for the next step boundary."""
        return self._control.pop(run_id, None)

    async def shutdown(self) -> None:
        """Graceful stop: cancel in-flight steps and mark those runs interrupted."""
        running = {rid: t for rid, t in self._tasks.items() if not t.done()}
        for t in running.values():
            t.cancel()
        await asyncio.gather(*running.values(), return_exceptions=True)
        for rid in running:
            st = self.store.load(rid)
            if st and st["status"] == "running":
                self._set_status(
                    st,
                    "interrupted",
                    "The server shut down during this step. Resume to continue from the last checkpoint.",
                )

    # ---- lifecycle -------------------------------------------------------------------------
    def recover(self) -> int:
        """On startup, mark runs that were mid-flight when the process died."""
        n = 0
        for st in self.store.runs_with_status(["running", "queued"]):
            self._set_status(
                st,
                "interrupted",
                "The server stopped while this run was in progress. Resume to continue from the last checkpoint.",
            )
            n += 1
        # Mid-approval crash: intent was checkpointed (pending.executing) but the process died
        # before clearing the gate. Surface as interrupted so Resume finishes idempotently.
        for st in self.store.runs_with_status(["awaiting_approval"]):
            p = st.get("pending") or {}
            if p.get("kind") == "approval" and p.get("executing"):
                self._set_status(
                    st,
                    "interrupted",
                    "The server stopped while applying an approved change. Resume to finish the idempotent apply.",
                )
                n += 1
        return n

    def create_run(self, scenario_id: str) -> dict:
        try:
            scenario = self._load_scenario(scenario_id)
        except KeyError as e:
            raise NotFound(str(e).strip("'\"")) from None
        active = sum(1 for t in self._tasks.values() if not t.done())
        if active >= self.settings.max_concurrent_runs:
            raise TooBusy(
                f"{active} runs are already active (limit {self.settings.max_concurrent_runs}). Try again shortly."
            )
        st = new_run_state(make_run_id(), scenario, self.settings)
        st["recalled_memories"] = self.store.recall([st["service"]], self.settings.memory_ttl_days, 3)
        self.store.create_run(st)
        self._emit(
            st,
            "run.created",
            {"task": st["task"], "scenario": scenario_id, "provider": self.llm.provider, "model": self.llm.model},
        )
        if st["recalled_memories"]:
            self._emit(st, "memory.recalled", {"memories": st["recalled_memories"]})
        self._launch(st["run_id"])
        return st

    def pause(self, run_id: str) -> None:
        st = self.get(run_id)
        if not self.is_active(run_id):
            raise RunStateError(f"Run is {st['status']}; only a running run can be paused")
        self._control[run_id] = "pause"
        self._emit(st, "operator.control", {"action": "pause"})

    def cancel(self, run_id: str) -> None:
        """Stop a run. Prefer step-boundary cancel via the prepare node; also cancel the
        in-flight asyncio task so a long LLM/tool await does not keep burning tokens.
        Does not roll back an already-applied production mutation.
        """
        st = self.get(run_id)
        if st["status"] in TERMINAL:
            raise RunStateError(f"Run is already {st['status']}")
        self._control[run_id] = "cancel"
        self._emit(st, "operator.control", {"action": "cancel"})
        t = self._tasks.get(run_id)
        if t is not None and not t.done():
            t.cancel()
            return
        # Idle (e.g. awaiting_approval / paused): flip immediately.
        st["pending"] = None
        self._set_status(st, "cancelled", "Cancelled by operator")

    def emergency_stop(self) -> dict:
        """Cancel every non-terminal run. Per-run kill switch applied fleet-wide."""
        cancelled: list[str] = []
        skipped: list[str] = []
        for row in self.store.list_runs(limit=500):
            rid = row["id"]
            st = self.store.load(rid)
            if not st:
                continue
            if st["status"] in TERMINAL:
                skipped.append(rid)
                continue
            try:
                self.cancel(rid)
                cancelled.append(rid)
            except RunStateError:
                skipped.append(rid)
        return {"cancelled": cancelled, "skipped": skipped}

    def resume(self, run_id: str) -> None:
        st = self.get(run_id)
        if self.is_active(run_id) or st["status"] not in RESUMABLE:
            raise RunStateError(f"Run is {st['status']} and cannot be resumed")
        if st["status"] == "needs_attention":
            if st["step"] >= st["max_steps"]:
                st["max_steps"] += 10
            used = st["usage"]["input_tokens"] + st["usage"]["output_tokens"]
            if used >= st["max_run_tokens"]:
                st["max_run_tokens"] = int(st["max_run_tokens"] * 1.5)
            if self.settings.max_run_cost_usd > 0 and st["usage"]["cost_usd"] >= self.settings.max_run_cost_usd:
                # Persist a raised ceiling on the run itself so resume is meaningful.
                st["max_run_cost_usd"] = round(st.get("max_run_cost_usd", self.settings.max_run_cost_usd) * 1.5, 4)
        p = st.get("pending")
        if p:
            # Crash mid-approval: mutation may already be applied (idempotent by tool-call id).
            # Finish the gate without asking the operator to click Approve again.
            if p.get("kind") == "approval" and p.get("executing"):
                self._emit(st, "operator.control", {"action": "resume", "complete_interrupted_approval": True})
                self.approve(run_id, p.get("final_args"), actor="system-resume")
                return
            kind = "awaiting_approval" if p["kind"] == "approval" else "awaiting_input"
            self._set_status(st, kind, "Restored the pending operator decision from the checkpoint")
            return
        self._emit(st, "operator.control", {"action": "resume"})
        self.store.save(st)
        self._launch(run_id)

    # ---- human-in-the-loop -------------------------------------------------------------------
    def approve(self, run_id: str, edited_args: dict | None = None, actor: str = "operator") -> None:
        """Resume the LangGraph approval interrupt with an approve decision.

        Argument validation happens here so the HTTP API can 422 before the
        graph runs. The gate node performs the idempotent production apply.
        Idempotent when the gate was already claimed (double-click / retry).
        """

        with self._gate_lock(run_id):
            st = self.get(run_id)
            p = st.get("pending")
            # Already claimed — treat as success so clients can safely retry.
            if p and p.get("kind") == "approval" and (p.get("submitted") or run_id in self._pending_resume):
                if run_id not in self._pending_resume and not self.is_active(run_id):
                    # Submitted flag stuck without a resume payload — relaunch.
                    self._launch(run_id)
                return
            can_finish = (st["status"] == "awaiting_approval" and p and p.get("kind") == "approval") or (
                p and p.get("kind") == "approval" and p.get("executing")
            )
            if not can_finish:
                raise RunStateError(f"Run is {st['status']}; nothing is waiting for approval")
            assert p is not None  # narrowed by can_finish
            spec = TOOLS[p["tool"]]
            base_args = p.get("final_args") or p["args"]
            try:
                spec.parse({**base_args, **(edited_args or {})})
            except ToolArgsError as e:
                raise InvalidInput(f"Edited arguments are invalid: {e}") from None
            # Claim the gate immediately so a double-click is idempotent above.
            p["submitted"] = True
            try:
                self.store.save(st)
            except ConcurrencyConflict:
                st = self.get(run_id)
                p = st.get("pending") or p
                p["submitted"] = True
                st["pending"] = p
                self.store.save(st)
            self._pending_resume[run_id] = {
                "decision": "approved",
                "args": edited_args,
                "actor": actor,
            }
            self._launch(run_id)

    def reject(self, run_id: str, feedback: str = "", actor: str = "operator") -> None:
        with self._gate_lock(run_id):
            st = self.get(run_id)
            p = st.get("pending")
            if st["status"] != "awaiting_approval" or not p or p["kind"] != "approval":
                raise RunStateError(f"Run is {st['status']}; nothing is waiting for approval")
            if p.get("executing") or p.get("submitted"):
                raise RunStateError("This approval is already executing and cannot be rejected; resume to finish it.")
            if run_id in self._pending_resume:
                raise RunStateError(f"Run is {st['status']}; nothing is waiting for approval")
            p["submitted"] = True
            self.store.save(st)
            self._pending_resume[run_id] = {
                "decision": "rejected",
                "feedback": (feedback or "").strip(),
                "actor": actor,
            }
            self._launch(run_id)

    def message(self, run_id: str, text: str, actor: str = "operator") -> None:
        text = (text or "").strip()
        if not text:
            raise InvalidInput("Message is empty")
        st = self.get(run_id)
        if st["status"] in TERMINAL:
            raise RunStateError(f"Run is {st['status']}")
        p = st.get("pending")
        if st["status"] == "awaiting_input" and p and p["kind"] == "input":
            self._pending_resume[run_id] = {"decision": "message", "text": text, "actor": actor}
            self._launch(run_id)
            return
        self.store.push_inbox(run_id, text)
        self._emit(st, "operator.message", {"text": text, "queued": True, "actor": actor})

    # ---- the loop --------------------------------------------------------------------------------

    def _publish_gate_if_needed(self, run_id: str) -> None:
        """Flip Store status to awaiting_* only after the interrupt is checkpointed."""
        st = self.get(run_id)
        p = st.get("pending")
        if not p or st["status"] in ("awaiting_approval", "awaiting_input"):
            return
        if p.get("kind") == "approval":
            enriched = self._present_pending(p)
            self._emit(st, "approval.requested", enriched)
            self._set_status(
                st,
                "awaiting_approval",
                "Waiting for you to approve a production change.",
            )
        elif p.get("kind") == "input":
            self._emit(st, "input.requested", self._present_pending(p))
            self._set_status(st, "awaiting_input", "The agent asked the operator a question.")

    def _launch(self, run_id: str) -> None:
        t = self._tasks.get(run_id)
        if t is not None and not t.done():
            # Current drive is still unwinding (e.g. just parked on needs_attention).
            # Relaunch from finally so we never run two checkpointers on one thread.
            self._relaunch.add(run_id)
            return
        self._tasks[run_id] = asyncio.get_running_loop().create_task(self._drive(run_id))

    async def _drive(self, run_id: str) -> None:
        """Run the LangGraph until END or an interrupt (human gate).

        Approve/reject may race with the interrupt return: they stash a payload in
        `_pending_resume` and call `_launch`. We drain that payload here, and if a
        payload arrives in the finally window we re-schedule ourselves.
        """
        try:
            async with self._checkpointer_factory(self.settings) as saver:
                graph = build_agent_graph(saver)
                config = {"configurable": {"thread_id": run_id, "runtime": self}}
                while True:
                    resume = self._pending_resume.pop(run_id, None)
                    if resume is not None:
                        await graph.ainvoke(Command(resume=resume), config)
                    else:
                        snap = await graph.aget_state(config)
                        if snap.next:
                            st = self.get(run_id)
                            if st["status"] in ("awaiting_approval", "awaiting_input"):
                                # Parked on a human gate — exit; approve/reject will relaunch.
                                return
                            await graph.ainvoke(None, config)
                        else:
                            st = self.get(run_id)
                            if st["status"] in TERMINAL:
                                return
                            if st["status"] in ("awaiting_approval", "awaiting_input"):
                                return
                            # paused / needs_attention / interrupted / queued → continue
                            if st["status"] != "running":
                                self._set_status(st, "running")
                            await graph.ainvoke(st, config)

                    self._publish_gate_if_needed(run_id)
                    if run_id in self._pending_resume:
                        continue
                    st = self.get(run_id)
                    if st["status"] in ("awaiting_approval", "awaiting_input"):
                        return
                    if st["status"] in TERMINAL | {"paused", "needs_attention", "interrupted"}:
                        return
                    # Graph ended a continue-cycle at END while still marked running —
                    # should be rare; avoid a tight loop.
                    if st["status"] == "running":
                        continue
                    return
        except asyncio.CancelledError:
            # Operator cancel sets _control["cancel"] then cancels the task.
            # Process shutdown cancels without that flag; recover() marks interrupted.
            if self._control.pop(run_id, None) == "cancel":
                cur = self.store.load(run_id)
                if cur is not None and cur["status"] not in TERMINAL:
                    cur["pending"] = None
                    self._set_status(cur, "cancelled", "Cancelled by operator")
                return
            raise
        except Exception as e:  # noqa: BLE001
            log.exception("run %s failed", run_id)
            st = self.get(run_id)
            st["error"] = f"{type(e).__name__}: {e}"
            self._set_status(st, "failed", f"{st['error']}. Resume to retry from the last checkpoint.")
        finally:
            self._tasks.pop(run_id, None)
            should = run_id in self._pending_resume or run_id in self._relaunch
            self._relaunch.discard(run_id)
            if should:
                try:
                    self._tasks[run_id] = asyncio.get_running_loop().create_task(self._drive(run_id))
                except RuntimeError:
                    pass

    # ---- step helpers (AgentRuntimePort) ------------------------------------------------
    async def call_llm(self, st: dict, messages: list[dict]) -> LLMResponse:
        return await self._llm_gateway.complete(st, messages)

    async def exec_read(self, st: dict, call: ToolCall, spec: ToolSpec) -> ToolOutcome:
        return await self._tool_executor.execute_read(st, call, spec, self.cluster(st))

    def gate(self, st: dict, call: ToolCall, spec: ToolSpec, step: int) -> dict | ToolOutcome:
        """Delegate write/input gating to the application policy helper (SRP)."""
        return build_gate_or_block(
            st,
            call,
            spec,
            step,
            min_write_confidence=self.settings.min_write_confidence,
            resolve_service=self.cluster(st).validate_service,
            emit=self._emit,
            present_pending=self._present_pending,
        )

    def apply_memory(self, st: dict, call: ToolCall, spec: ToolSpec) -> ToolOutcome:
        from app.tools.specs import MemoryArgs

        try:
            args = cast(MemoryArgs, spec.parse(call.args))
        except ToolArgsError as e:
            return (f"Invalid arguments for update_working_memory: {e}", True, {})
        changed = apply_working_memory(st, args)
        self._emit(
            st,
            "memory.update",
            {"changed": changed, "plan": st["plan"], "hypotheses": st["hypotheses"], "note": args.note},
        )
        return ("Working memory updated: " + (", ".join(changed) or "no changes"), False, {})

    def record(self, st: dict, step: int, call: ToolCall, content: str, is_error: bool, meta: dict) -> None:
        self._tool_executor.record(st, step, call, content, is_error, meta)

    def finish(self, st: dict, result: dict) -> None:
        result["sim_resolved"] = self.cluster(st).resolved()  # simulator ground truth, shown for evaluation only
        st["result"] = result
        if result["resolved"]:
            mem = make_memory(st, result)
            self.store.add_memory(st["service"], st["run_id"], mem)
            self._emit(st, "memory.saved", {"memory": mem})
        self._emit(st, "run.finished", {"result": result, "usage": st["usage"]})
        self._set_status(
            st,
            "completed",
            "The agent reports the incident resolved"
            if result["resolved"]
            else "The agent finished without resolving the incident",
        )

    def maybe_budget_alert(self, st: dict) -> None:
        """Emit a one-shot budget.alert as usage crosses the configured ratio of each ceiling."""
        ratio = self.settings.budget_alert_ratio
        alerts = set(st.get("budget_alerts") or [])
        for c in budget_crossings(
            st, ratio=ratio, default_cost_cap=self.settings.max_run_cost_usd, already_alerted=alerts
        ):
            alerts.add(c.budget)
            st["budget_alerts"] = sorted(alerts)
            self._emit(
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

    def cluster(self, st: dict) -> ClusterPort:
        """Adapter factory: bind the platform adapter to this run's scenario and env checkpoint."""
        return self._cluster_factory(st["scenario_id"], st["env"])

    # ---- events --------------------------------------------------------------------------
    def set_status(self, st: dict, status: str, reason: str | None = None) -> None:
        self.events.set_status(st, status, reason)

    def emit(self, st: dict, type_: str, payload: dict) -> None:
        self.events.emit(st, type_, payload)

    # Internal short names used throughout the lifecycle methods above.
    _set_status = set_status
    _emit = emit
