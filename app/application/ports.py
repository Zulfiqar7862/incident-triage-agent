"""Contracts owned by the application layer (Dependency Inversion).

The application depends on these Protocols and callable aliases; the composition
root (``app.core.container``) supplies concrete adapters. Domain-level ports
(``RunStorePort``, ``ClusterPort``, ``LLMPort``) live in ``app.domain.ports``.
"""

from __future__ import annotations

from collections.abc import Callable, Iterator, Mapping
from contextlib import AbstractAsyncContextManager, AbstractContextManager, contextmanager
from dataclasses import dataclass, field
from typing import Any, Protocol, runtime_checkable

from app.core.config import Settings
from app.domain.llm import LLMResponse, ToolCall
from app.domain.ports import ClusterPort

ToolOutcome = tuple[str, bool, dict[str, Any]]
"""(content shown to the model, is_error, metadata such as attempts and duration)."""

ClusterFactory = Callable[[str, dict], ClusterPort]
ScenarioLoader = Callable[[str], dict]
ScenarioCatalog = Callable[[], list[dict]]
CheckpointerFactory = Callable[[Settings], AbstractAsyncContextManager[Any]]
PendingPresenter = Callable[[dict], dict]
"""Adds operator-facing fields to a pending approval or question."""


@dataclass
class DispatchResult:
    """What one batch of tool calls produced, for the act node to route on."""

    pending: dict | None = None
    """An approval or operator question opened by this batch (at most one)."""
    finish: dict | None = None
    """Validated ``finish`` arguments when the agent ended the run."""
    loop_stop_reason: str | None = None
    """Set when the loop guard saw the same call repeated too often."""
    outcomes: dict[str, ToolOutcome] = field(default_factory=dict)


class ToolPresenter(Protocol):
    """Plain-English labels for a tool call, attached to audit events for the UI."""

    def __call__(
        self, name: str, args: Mapping[str, Any] | None = None, *, kind: str | None = None
    ) -> dict[str, str]: ...


def no_tool_labels(name: str, args: Mapping[str, Any] | None = None, *, kind: str | None = None) -> dict[str, str]:
    """Default ``ToolPresenter`` used when no presentation layer is wired (unit tests)."""
    return {}


@runtime_checkable
class TelemetryPort(Protocol):
    """Metrics and tracing sink. Implemented by ``infrastructure.observability``."""

    def span(self, name: str, **attrs: Any) -> AbstractContextManager[dict[str, Any]]: ...

    def llm_call(
        self, model: str, input_tokens: int, output_tokens: int, cost_usd: float, latency_s: float
    ) -> None: ...

    def tool_call(self, tool: str, is_error: bool) -> None: ...

    def approval(self, decision: str) -> None: ...

    def export(self, run_counts: dict[str, int], event_counts: dict[str, int]) -> tuple[bytes, str]: ...


class NullTelemetry:
    """Null Object for ``TelemetryPort``: records nothing."""

    @contextmanager
    def span(self, name: str, **attrs: Any) -> Iterator[dict[str, Any]]:
        yield dict(attrs)

    def llm_call(self, model: str, input_tokens: int, output_tokens: int, cost_usd: float, latency_s: float) -> None:
        return None

    def tool_call(self, tool: str, is_error: bool) -> None:
        return None

    def approval(self, decision: str) -> None:
        return None

    def export(self, run_counts: dict[str, int], event_counts: dict[str, int]) -> tuple[bytes, str]:
        return b"", "text/plain; charset=utf-8"


@runtime_checkable
class AgentStepsPort(Protocol):
    """Operations the LangGraph nodes may call during one step (Interface Segregation).

    Nodes see this Protocol only, never ``RunService`` or the Store.
    """

    def load(self, run_id: str) -> dict: ...

    def save(self, st: dict) -> None: ...

    def take_control(self, run_id: str) -> str | None: ...

    def apply_control(self, st: dict, action: str) -> bool: ...

    def stop_if_over_budget(self, st: dict) -> bool: ...

    def maybe_budget_alert(self, st: dict) -> None: ...

    def set_status(self, st: dict, status: str, reason: str | None = None) -> None: ...

    def drain_inbox(self, st: dict, step: int) -> list[int]: ...

    def ack_inbox(self, acks: list[int]) -> None: ...

    def build_messages(self, st: dict) -> list[dict]: ...

    async def call_llm(self, st: dict, messages: list[dict]) -> LLMResponse: ...

    def record_assistant(self, st: dict, resp: LLMResponse, step: int) -> None: ...

    def nudge(self, st: dict, step: int) -> str: ...

    async def dispatch(self, st: dict, calls: list[ToolCall], step: int) -> DispatchResult: ...

    def conclude(self, st: dict, result: DispatchResult) -> str: ...

    def resolve_approval(self, st: dict, pending: dict | None, decision: dict | None) -> None: ...

    def resolve_answer(self, st: dict, pending: dict | None, decision: dict | None) -> None: ...
