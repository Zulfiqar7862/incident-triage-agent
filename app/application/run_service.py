"""Run lifecycle use cases behind the HTTP API: create, pause, resume, cancel,
emergency stop, approve, reject, message. Reads live in ``run_queries``.

Lifecycle
    queued -> running -> (awaiting_approval | awaiting_input | paused | needs_attention)
           -> running -> completed | failed | cancelled
    A server restart turns "running" into "interrupted"; resume continues from the
    last LangGraph checkpoint and the Store checkpoint.

The service validates a command, updates durable state, and hands execution to
``GraphRunner``. It imports no infrastructure or presentation code; every
collaborator arrives through the constructor (see ``app.core.container``).
"""

from __future__ import annotations

from collections.abc import Mapping

from app.application.agent.state import make_run_id, new_run_state
from app.application.events import RunEventRecorder
from app.application.exceptions import ConcurrencyConflict, InvalidInput, NotFound, RunStateError, TooBusy
from app.application.graph_runner import GraphRunner
from app.application.ports import AgentStepsPort, ScenarioLoader
from app.application.run_controls import GateLocks, RunControls
from app.application.run_queries import RunQueries
from app.application.tools import ToolArgsError, ToolSpec
from app.core.config import Settings
from app.domain.lifecycle import RESUMABLE, TERMINAL
from app.domain.ports import RunStorePort


class RunService:
    """Write side of the run lifecycle (commands). One instance per process.

    Reads go through ``RunQueries``; execution is delegated to ``GraphRunner``.
    """

    def __init__(
        self,
        *,
        store: RunStorePort,
        settings: Settings,
        events: RunEventRecorder,
        runner: GraphRunner,
        steps: AgentStepsPort,
        controls: RunControls,
        tools: Mapping[str, ToolSpec],
        queries: RunQueries,
        scenario_loader: ScenarioLoader,
    ) -> None:
        self._store = store
        self.settings = settings
        self._events = events
        self.runner = runner
        self.steps = steps
        self._controls = controls
        self._tools = tools
        self.queries = queries
        self._load_scenario = scenario_loader
        self._gate_locks = GateLocks()

    # ---- lookups used by the commands ------------------------------------------------------
    def get(self, run_id: str) -> dict:
        return self.queries.get(run_id)

    def is_active(self, run_id: str) -> bool:
        return self.queries.is_active(run_id)

    # ---- process lifecycle -------------------------------------------------------------------
    def recover(self) -> int:
        """On startup, mark runs that were mid-flight when the process died."""
        n = 0
        for st in self._store.runs_with_status(["running", "queued"]):
            self._events.set_status(
                st,
                "interrupted",
                "The server stopped while this run was in progress. Resume to continue from the last checkpoint.",
            )
            n += 1
        # Mid-approval crash: the intent was checkpointed (pending.executing) but the process
        # died before clearing the gate. Surface it as interrupted so Resume finishes idempotently.
        for st in self._store.runs_with_status(["awaiting_approval"]):
            p = st.get("pending") or {}
            if p.get("kind") == "approval" and p.get("executing"):
                self._events.set_status(
                    st,
                    "interrupted",
                    "The server stopped while applying an approved change. Resume to finish the idempotent apply.",
                )
                n += 1
        return n

    async def shutdown(self) -> None:
        """Graceful stop: cancel in-flight steps and mark those runs interrupted."""
        for rid in await self.runner.shutdown():
            st = self._store.load(rid)
            if st and st["status"] == "running":
                self._events.set_status(
                    st,
                    "interrupted",
                    "The server shut down during this step. Resume to continue from the last checkpoint.",
                )

    # ---- run commands ------------------------------------------------------------------------
    def create_run(self, scenario_id: str) -> dict:
        try:
            scenario = self._load_scenario(scenario_id)
        except KeyError as e:
            raise NotFound(str(e).strip("'\"")) from None
        active = self.runner.active_count()
        if active >= self.settings.max_concurrent_runs:
            raise TooBusy(
                f"{active} runs are already active (limit {self.settings.max_concurrent_runs}). Try again shortly."
            )
        st = new_run_state(make_run_id(), scenario, self.settings)
        st["recalled_memories"] = self._store.recall([st["service"]], self.settings.memory_ttl_days, 3)
        self._store.create_run(st)
        self._events.emit(st, "run.created", {"task": st["task"], "scenario": scenario_id, **self.queries.model_info})
        if st["recalled_memories"]:
            self._events.emit(st, "memory.recalled", {"memories": st["recalled_memories"]})
        self.runner.launch(st["run_id"])
        return st

    def pause(self, run_id: str) -> None:
        st = self.get(run_id)
        if not self.is_active(run_id):
            raise RunStateError(f"Run is {st['status']}; only a running run can be paused")
        self._controls.request(run_id, "pause")
        self._events.emit(st, "operator.control", {"action": "pause"})

    def cancel(self, run_id: str) -> None:
        """Stop a run at the next step boundary and cancel any in-flight LLM or tool await.

        Does not roll back a production change that was already applied.
        """
        st = self.get(run_id)
        if st["status"] in TERMINAL:
            raise RunStateError(f"Run is already {st['status']}")
        self._controls.request(run_id, "cancel")
        self._events.emit(st, "operator.control", {"action": "cancel"})
        if self.runner.cancel_task(run_id):
            return
        # Idle (awaiting approval, paused, ...): flip immediately.
        st["pending"] = None
        self._events.set_status(st, "cancelled", "Cancelled by operator")

    def emergency_stop(self) -> dict:
        """Cancel every non-terminal run (the per-run kill switch, fleet-wide)."""
        cancelled: list[str] = []
        skipped: list[str] = []
        for row in self._store.list_runs(limit=500):
            rid = row["id"]
            st = self._store.load(rid)
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
            self._raise_exhausted_ceilings(st)
        p = st.get("pending")
        if p:
            # Crash mid-approval: the change may already be applied (idempotent by tool-call id).
            # Finish the gate without asking the operator to click Approve again.
            if p.get("kind") == "approval" and p.get("executing"):
                self._events.emit(st, "operator.control", {"action": "resume", "complete_interrupted_approval": True})
                self.approve(run_id, p.get("final_args"), actor="system-resume")
                return
            kind = "awaiting_approval" if p["kind"] == "approval" else "awaiting_input"
            self._events.set_status(st, kind, "Restored the pending operator decision from the checkpoint")
            return
        self._events.emit(st, "operator.control", {"action": "resume"})
        self._store.save(st)
        self.runner.launch(run_id)

    def _raise_exhausted_ceilings(self, st: dict) -> None:
        """Grant headroom on the ceiling that parked the run, so Resume is meaningful."""
        if st["step"] >= st["max_steps"]:
            st["max_steps"] += 10
        used = st["usage"]["input_tokens"] + st["usage"]["output_tokens"]
        if used >= st["max_run_tokens"]:
            st["max_run_tokens"] = int(st["max_run_tokens"] * 1.5)
        cap = self.settings.max_run_cost_usd
        if cap > 0 and st["usage"]["cost_usd"] >= cap:
            st["max_run_cost_usd"] = round(st.get("max_run_cost_usd", cap) * 1.5, 4)

    # ---- human-in-the-loop -------------------------------------------------------------------
    def approve(self, run_id: str, edited_args: dict | None = None, actor: str = "operator") -> None:
        """Resume the approval interrupt with an approve decision.

        Arguments are validated here so the HTTP API can return 422 before the graph
        runs; the gate node performs the idempotent production change. Idempotent when
        the gate was already claimed (double-click, client retry).
        """
        with self._gate_locks.for_run(run_id):
            st = self.get(run_id)
            p = st.get("pending")
            queued = self.runner.has_queued_resume(run_id)
            if p and p.get("kind") == "approval" and (p.get("submitted") or queued):
                if not queued and not self.is_active(run_id):
                    self.runner.launch(run_id)  # submitted flag stuck without a resume payload
                return
            can_finish = (st["status"] == "awaiting_approval" and p and p.get("kind") == "approval") or (
                p and p.get("kind") == "approval" and p.get("executing")
            )
            if not can_finish or p is None:
                raise RunStateError(f"Run is {st['status']}; nothing is waiting for approval")
            base_args = p.get("final_args") or p["args"]
            try:
                self._tools[p["tool"]].parse({**base_args, **(edited_args or {})})
            except ToolArgsError as e:
                raise InvalidInput(f"Edited arguments are invalid: {e}") from None
            self._claim_gate(run_id, st, p)
            self.runner.queue_resume(run_id, {"decision": "approved", "args": edited_args, "actor": actor})

    def reject(self, run_id: str, feedback: str = "", actor: str = "operator") -> None:
        with self._gate_locks.for_run(run_id):
            st = self.get(run_id)
            p = st.get("pending")
            if st["status"] != "awaiting_approval" or not p or p["kind"] != "approval":
                raise RunStateError(f"Run is {st['status']}; nothing is waiting for approval")
            if p.get("executing") or p.get("submitted"):
                raise RunStateError("This approval is already executing and cannot be rejected; resume to finish it.")
            if self.runner.has_queued_resume(run_id):
                raise RunStateError(f"Run is {st['status']}; nothing is waiting for approval")
            p["submitted"] = True
            self._store.save(st)
            self.runner.queue_resume(
                run_id, {"decision": "rejected", "feedback": (feedback or "").strip(), "actor": actor}
            )

    def message(self, run_id: str, text: str, actor: str = "operator") -> None:
        """Answer a pending question, or queue guidance for the agent's next step."""
        text = (text or "").strip()
        if not text:
            raise InvalidInput("Message is empty")
        st = self.get(run_id)
        if st["status"] in TERMINAL:
            raise RunStateError(f"Run is {st['status']}")
        p = st.get("pending")
        if st["status"] == "awaiting_input" and p and p["kind"] == "input":
            self.runner.queue_resume(run_id, {"decision": "message", "text": text, "actor": actor})
            return
        self._store.push_inbox(run_id, text)
        self._events.emit(st, "operator.message", {"text": text, "queued": True, "actor": actor})

    def _claim_gate(self, run_id: str, st: dict, p: dict) -> None:
        """Mark the gate submitted so a double-click is idempotent; retry once on a CAS conflict."""
        p["submitted"] = True
        try:
            self._store.save(st)
        except ConcurrencyConflict:
            st = self.get(run_id)
            p = st.get("pending") or p
            p["submitted"] = True
            st["pending"] = p
            self._store.save(st)
