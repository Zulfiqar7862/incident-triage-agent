"""Route one model turn's tool calls to handlers through a registry (Open/Closed).

Before: ``act_node`` decided behaviour with an if/elif chain on tool kind and
name. Now each route is a handler registered by tool name or kind; adding a tool
of an existing kind needs no change here, and a new kind is one ``register`` call.
"""

from __future__ import annotations

import asyncio
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from typing import cast

from app.application.events import RunEventRecorder
from app.application.ports import DispatchResult, ToolOutcome, ToolPresenter
from app.application.tool_executor import ToolExecutor
from app.application.tools import ToolArgsError, ToolSpec
from app.application.tools.specs import MemoryArgs
from app.application.working_memory import apply_working_memory
from app.application.write_gate import WriteGate
from app.domain.guards import LoopGuard
from app.domain.llm import ToolCall
from app.domain.ports import ClusterPort

ONE_GATE_AT_A_TIME = (
    "Not executed: only one production change or operator question can be pending at a time. "
    "Re-issue it after the current one is resolved."
)


@dataclass
class _Batch:
    """Mutable scratchpad for one model turn's tool calls."""

    st: dict
    step: int
    outcomes: dict[str, ToolOutcome] = field(default_factory=dict)
    reads: list[tuple[ToolCall, ToolSpec]] = field(default_factory=list)
    pending: dict | None = None
    finish_call: ToolCall | None = None


ToolHandler = Callable[[_Batch, ToolCall, ToolSpec], None]


class ToolCallDispatcher:
    """Runs a batch of tool calls: reads in parallel, at most one human gate, then finish.

    Handlers are looked up by tool name first, then by tool kind.
    """

    def __init__(
        self,
        *,
        tools: Mapping[str, ToolSpec],
        executor: ToolExecutor,
        write_gate: WriteGate,
        events: RunEventRecorder,
        cluster_for: Callable[[dict], ClusterPort],
        present_tool: ToolPresenter,
        max_identical_calls: int,
    ) -> None:
        self._tools = tools
        self._executor = executor
        self._gate = write_gate
        self._events = events
        self._cluster_for = cluster_for
        self._present_tool = present_tool
        self._max_identical = max_identical_calls
        self._handlers: dict[str, ToolHandler] = {}
        self.register("read", self._queue_read)
        self.register("write", self._open_gate)
        self.register("ask_operator", self._open_gate)
        self.register("update_working_memory", self._update_memory)
        self.register("finish", self._queue_finish)

    def register(self, key: str, handler: ToolHandler) -> None:
        """Bind a handler to a tool name or a tool kind."""
        self._handlers[key] = handler

    def handler_for(self, spec: ToolSpec) -> ToolHandler:
        """Name-specific handler if registered, else the handler for the tool's kind."""
        handler = self._handlers.get(spec.name) or self._handlers.get(spec.kind)
        if handler is None:
            raise LookupError(f"No dispatch handler for tool '{spec.name}' (kind {spec.kind})")
        return handler

    async def dispatch(self, st: dict, calls: list[ToolCall], step: int) -> DispatchResult:
        """Announce, execute, and record every call; return what the act node must route on."""
        self._announce(st, calls)
        batch = _Batch(st=st, step=step)
        for call in calls:
            spec = self._tools.get(call.name)
            if spec is None:
                batch.outcomes[call.id] = (
                    f"Unknown tool '{call.name}'. Available tools: {', '.join(self._tools)}",
                    True,
                    {},
                )
                continue
            self.handler_for(spec)(batch, call, spec)
        await self._run_reads(batch)
        finish = self._resolve_finish(batch)
        for call in calls:
            if call.id in batch.outcomes:
                self._executor.record(st, step, call, *batch.outcomes[call.id])
        loop_stop = self._loop_guard(st, calls, batch)
        return DispatchResult(
            pending=batch.pending,
            finish=finish,
            loop_stop_reason=loop_stop if finish is None and batch.pending is None else None,
            outcomes=batch.outcomes,
        )

    # ---- handlers -----------------------------------------------------------------------
    def _queue_read(self, batch: _Batch, call: ToolCall, spec: ToolSpec) -> None:
        batch.reads.append((call, spec))

    def _queue_finish(self, batch: _Batch, call: ToolCall, spec: ToolSpec) -> None:
        batch.finish_call = call

    def _update_memory(self, batch: _Batch, call: ToolCall, spec: ToolSpec) -> None:
        st = batch.st
        try:
            args = cast(MemoryArgs, spec.parse(call.args))
        except ToolArgsError as e:
            batch.outcomes[call.id] = (f"Invalid arguments for update_working_memory: {e}", True, {})
            return
        changed = apply_working_memory(st, args)
        self._events.emit(
            st,
            "memory.update",
            {"changed": changed, "plan": st["plan"], "hypotheses": st["hypotheses"], "note": args.note},
        )
        batch.outcomes[call.id] = ("Working memory updated: " + (", ".join(changed) or "no changes"), False, {})

    def _open_gate(self, batch: _Batch, call: ToolCall, spec: ToolSpec) -> None:
        if batch.pending is not None:
            batch.outcomes[call.id] = (ONE_GATE_AT_A_TIME, True, {})
            return
        outcome = self._gate.open(
            batch.st, call, spec, batch.step, resolve_service=self._cluster_for(batch.st).validate_service
        )
        if isinstance(outcome, tuple):
            batch.outcomes[call.id] = outcome
        else:
            batch.pending = outcome

    # ---- phases ---------------------------------------------------------------------------
    def _announce(self, st: dict, calls: list[ToolCall]) -> None:
        for call in calls:
            spec = self._tools.get(call.name)
            kind = spec.kind if spec else None
            self._events.emit(
                st,
                "tool.call",
                {
                    "id": call.id,
                    "name": call.name,
                    "args": call.args,
                    "kind": kind or "unknown",
                    **self._present_tool(call.name, call.args, kind=kind),
                },
            )

    async def _run_reads(self, batch: _Batch) -> None:
        if not batch.reads:
            return
        outs = await asyncio.gather(
            *(self._executor.execute_read(batch.st, c, spec, self._cluster_for(batch.st)) for c, spec in batch.reads)
        )
        for (call, _), out in zip(batch.reads, outs, strict=True):
            batch.outcomes[call.id] = out

    def _resolve_finish(self, batch: _Batch) -> dict | None:
        call = batch.finish_call
        if call is None:
            return None
        if batch.pending is not None:
            batch.outcomes[call.id] = ("Not finished: an operator decision is still pending.", True, {})
            return None
        try:
            done = self._tools["finish"].parse(call.args)
        except ToolArgsError as e:
            batch.outcomes[call.id] = (f"Invalid arguments for finish: {e}", True, {})
            return None
        batch.outcomes[call.id] = ("Run finished.", False, {})
        return done.model_dump()

    def _loop_guard(self, st: dict, calls: list[ToolCall], batch: _Batch) -> str | None:
        guard = LoopGuard(self._max_identical)
        guard.loads(st.get("loop_guard"))
        for call in calls:
            if call.id in batch.outcomes:
                guard.record(call.name, call.args)
        st["loop_guard"] = guard.dumps()
        stop, reason = guard.should_stop()
        return reason if stop else None
