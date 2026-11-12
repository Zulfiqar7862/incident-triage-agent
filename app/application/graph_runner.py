"""Supervises one asyncio task per run and drives the LangGraph until it parks or ends.

Owns: the task table, resume payloads queued by approve / reject / answer, the
relaunch set, and publishing a gate only after its interrupt is checkpointed.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from langgraph.graph.state import CompiledStateGraph
from langgraph.types import Command

from app.application.agent.graph import build_agent_graph
from app.application.events import RunEventRecorder
from app.application.exceptions import NotFound
from app.application.ports import AgentStepsPort, CheckpointerFactory, PendingPresenter
from app.application.run_controls import RunControls
from app.core.config import Settings
from app.domain.lifecycle import TERMINAL
from app.domain.ports import RunRepository

log = logging.getLogger("agent")

PARKED_ON_GATE = ("awaiting_approval", "awaiting_input")


class GraphRunner:
    """Template of a run: ``launch`` -> ``_drive`` loop -> park, end, or relaunch."""

    def __init__(
        self,
        *,
        runs: RunRepository,
        events: RunEventRecorder,
        steps: AgentStepsPort,
        controls: RunControls,
        settings: Settings,
        checkpointer_factory: CheckpointerFactory,
        present_pending: PendingPresenter = dict,
    ) -> None:
        self._runs = runs
        self._events = events
        self._steps = steps
        self._controls = controls
        self._settings = settings
        self._checkpointer_factory = checkpointer_factory
        self._present_pending = present_pending
        self._tasks: dict[str, asyncio.Task] = {}
        self._pending_resume: dict[str, dict] = {}
        self._relaunch: set[str] = set()

    # ---- queries ---------------------------------------------------------------------------
    def task_for(self, run_id: str) -> asyncio.Task | None:
        return self._tasks.get(run_id)

    def has_live_task(self, run_id: str) -> bool:
        t = self._tasks.get(run_id)
        return t is not None and not t.done()

    def active_count(self) -> int:
        return sum(1 for t in self._tasks.values() if not t.done())

    def has_queued_resume(self, run_id: str) -> bool:
        return run_id in self._pending_resume

    # ---- commands --------------------------------------------------------------------------
    def queue_resume(self, run_id: str, payload: dict) -> None:
        """Stash the operator decision for ``Command(resume=...)`` and make sure a task drains it."""
        self._pending_resume[run_id] = payload
        self.launch(run_id)

    def launch(self, run_id: str) -> None:
        if self.has_live_task(run_id):
            # The current drive is still unwinding (e.g. just parked on needs_attention).
            # Relaunch from its finally block so two checkpointers never share a thread.
            self._relaunch.add(run_id)
            return
        self._tasks[run_id] = asyncio.get_running_loop().create_task(self._drive(run_id))

    def cancel_task(self, run_id: str) -> bool:
        """Cancel the in-flight task, if any. Returns True when one was cancelled."""
        t = self._tasks.get(run_id)
        if t is None or t.done():
            return False
        t.cancel()
        return True

    async def shutdown(self) -> list[str]:
        """Cancel every live task and wait for it; returns the affected run ids."""
        running = {rid: t for rid, t in self._tasks.items() if not t.done()}
        for t in running.values():
            t.cancel()
        await asyncio.gather(*running.values(), return_exceptions=True)
        return list(running)

    # ---- the loop --------------------------------------------------------------------------
    async def _drive(self, run_id: str) -> None:
        """Run the graph until END or an interrupt (human gate).

        Approve / reject may race with the interrupt return: they queue a payload
        and call ``launch``. The loop drains it, and a payload that arrives in the
        ``finally`` window re-schedules the drive.
        """
        try:
            async with self._checkpointer_factory(self._settings) as saver:
                graph = build_agent_graph(saver)
                config = {"configurable": {"thread_id": run_id, "steps": self._steps}}
                while True:
                    if not await self._advance(graph, config, run_id):
                        return
                    self._publish_gate_if_needed(run_id)
                    if run_id in self._pending_resume:
                        continue
                    if self._load(run_id)["status"] != "running":
                        return
                    # The graph reached END while still marked running: loop again.
        except asyncio.CancelledError:
            # Operator cancel requests "cancel" then cancels the task. Process shutdown
            # cancels without that flag; ``RunService.recover`` marks those interrupted.
            if self._controls.take(run_id) == "cancel":
                cur = self._runs.load(run_id)
                if cur is not None and cur["status"] not in TERMINAL:
                    cur["pending"] = None
                    self._events.set_status(cur, "cancelled", "Cancelled by operator")
                return
            raise
        except Exception as e:  # noqa: BLE001 - any failure parks the run as failed and resumable
            log.exception("run %s failed", run_id)
            st = self._load(run_id)
            st["error"] = f"{type(e).__name__}: {e}"
            self._events.set_status(st, "failed", f"{st['error']}. Resume to retry from the last checkpoint.")
        finally:
            self._tasks.pop(run_id, None)
            should_relaunch = run_id in self._pending_resume or run_id in self._relaunch
            self._relaunch.discard(run_id)
            if should_relaunch:
                try:
                    self._tasks[run_id] = asyncio.get_running_loop().create_task(self._drive(run_id))
                except RuntimeError:
                    pass

    async def _advance(self, graph: CompiledStateGraph, config: Any, run_id: str) -> bool:
        """One ``ainvoke``: resume a gate, continue a checkpoint, or start fresh. False = stop driving."""
        resume = self._pending_resume.pop(run_id, None)
        if resume is not None:
            await graph.ainvoke(Command(resume=resume), config)
            return True
        snap = await graph.aget_state(config)
        st = self._load(run_id)
        if snap.next:
            if st["status"] in PARKED_ON_GATE:
                return False  # parked on a human gate; approve / reject relaunches
            await graph.ainvoke(None, config)
            return True
        if st["status"] in TERMINAL or st["status"] in PARKED_ON_GATE:
            return False
        # paused / needs_attention / interrupted / queued -> continue from the Store checkpoint
        if st["status"] != "running":
            self._events.set_status(st, "running")
        await graph.ainvoke(st, config)
        return True

    def _publish_gate_if_needed(self, run_id: str) -> None:
        """Flip status to awaiting_* only after the interrupt is checkpointed."""
        st = self._load(run_id)
        p = st.get("pending")
        if not p or st["status"] in PARKED_ON_GATE:
            return
        if p.get("kind") == "approval":
            self._events.emit(st, "approval.requested", self._present_pending(p))
            self._events.set_status(st, "awaiting_approval", "Waiting for you to approve a production change.")
        elif p.get("kind") == "input":
            self._events.emit(st, "input.requested", self._present_pending(p))
            self._events.set_status(st, "awaiting_input", "The agent asked the operator a question.")

    def _load(self, run_id: str) -> dict:
        st = self._runs.load(run_id)
        if st is None:
            raise NotFound(f"Run '{run_id}' not found")
        return st
