"""Inbound/outbound contracts of the application layer.

``AgentRuntimePort`` is what LangGraph nodes may call on the run service, so the
graph depends on an interface rather than the concrete ``RunService``. The
factory aliases describe adapters the composition root injects.
"""

from __future__ import annotations

from collections.abc import Callable
from contextlib import AbstractAsyncContextManager
from typing import Any, Protocol, runtime_checkable

from app.config import Settings
from app.domain.llm import LLMResponse, ToolCall
from app.domain.ports import ClusterPort, RunStorePort
from app.tools import ToolSpec

ToolOutcome = tuple[str, bool, dict[str, Any]]
ClusterFactory = Callable[[str, dict], ClusterPort]
ScenarioLoader = Callable[[str], dict]
ScenarioCatalog = Callable[[], list[dict]]
CheckpointerFactory = Callable[[Settings], AbstractAsyncContextManager[Any]]
PendingPresenter = Callable[[dict], dict]


@runtime_checkable
class AgentRuntimePort(Protocol):
    """Operations the graph nodes (``app.agent.nodes``) use during one step."""

    store: RunStorePort
    settings: Settings

    def get(self, run_id: str) -> dict: ...

    def take_control(self, run_id: str) -> str | None: ...

    def emit(self, st: dict, type_: str, payload: dict) -> None: ...

    def set_status(self, st: dict, status: str, reason: str | None = None) -> None: ...

    def maybe_budget_alert(self, st: dict) -> None: ...

    async def call_llm(self, st: dict, messages: list[dict]) -> LLMResponse: ...

    async def exec_read(self, st: dict, call: ToolCall, spec: ToolSpec) -> ToolOutcome: ...

    def gate(self, st: dict, call: ToolCall, spec: ToolSpec, step: int) -> dict | ToolOutcome: ...

    def apply_memory(self, st: dict, call: ToolCall, spec: ToolSpec) -> ToolOutcome: ...

    def record(self, st: dict, step: int, call: ToolCall, content: str, is_error: bool, meta: dict) -> None: ...

    def finish(self, st: dict, result: dict) -> None: ...

    def cluster(self, st: dict) -> ClusterPort: ...

    def tool_result_recorded(self, st: dict, tool_call_id: str) -> bool: ...
