"""Outbound ports (Protocols) implemented by infrastructure adapters.

The application layer depends only on these abstractions. ``RunStorePort`` is
split into role interfaces (``RunRepository``, ``EventLog``, ``OperatorInbox``,
``IncidentMemory``, ``StoreHealth``) so each collaborator asks only for what it uses. Concrete adapters: ``app.infrastructure.persistence.store.Store``
(RunStorePort), ``app.infrastructure.cluster.mock_cluster.MockCluster`` (ClusterPort),
and the providers in ``app.infrastructure.llm`` (LLMPort). No DI framework: adapters are
passed to constructors by the composition root (``app.core.container``).
"""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable

from app.domain.llm import LLMResponse


@runtime_checkable
class LLMPort(Protocol):
    """Strategy surface shared by Gemini / Anthropic / OpenAI / scripted providers."""

    @property
    def provider(self) -> str:
        """Provider name, e.g. ``gemini`` or ``scripted``."""
        ...

    @property
    def model(self) -> str:
        """Model identifier reported in events and the UI."""
        ...

    async def complete(
        self,
        system: str,
        messages: list[dict],
        tools: list[dict],
        state: dict | None = None,
    ) -> LLMResponse: ...


@runtime_checkable
class ClusterPort(Protocol):
    """Platform operations the tools call. ``MockCluster`` today; live adapters later."""

    def validate_service(self, name: str) -> None: ...

    def resolved(self) -> bool: ...

    def get_alert(self) -> dict: ...

    def list_services(self) -> list[dict]: ...

    def describe_service(self, service: str) -> dict: ...

    def query_metrics(self, service: str, metric: str, window_minutes: int = 60) -> dict: ...

    def search_logs(self, service: str, query: str, limit: int = 50) -> str: ...

    def search_runbooks(self, query: str, top_k: int = 2) -> list[dict]: ...

    def get_recent_deploys(self, service: str) -> dict: ...

    def rollback_deploy(self, service: str, to_version: str, action_id: str) -> dict: ...

    def restart_service(self, service: str, action_id: str) -> dict: ...


@runtime_checkable
class RunRepository(Protocol):
    """Durable run checkpoints with compare-and-swap saves."""

    def load(self, run_id: str) -> dict | None: ...

    def save(self, state: dict, *, cas: bool = True) -> None: ...

    def create_run(self, state: dict) -> None: ...

    def list_runs(self, limit: int = 50) -> list[dict]: ...

    def runs_with_status(self, statuses: list[str]) -> list[dict]: ...


@runtime_checkable
class EventLog(Protocol):
    """Append-only, hash-chained audit log of run events."""

    def append_event(self, run_id: str, type_: str, payload: dict[str, Any]) -> dict: ...

    def events_since(self, run_id: str, after: int = 0, limit: int = 500) -> list[dict]: ...

    def verify_event_chain(self, run_id: str) -> dict[str, Any]: ...


@runtime_checkable
class OperatorInbox(Protocol):
    """Operator messages queued for the next agent step (at-least-once delivery)."""

    def push_inbox(self, run_id: str, text: str) -> None: ...

    def peek_inbox(self, run_id: str) -> list[dict]: ...

    def ack_inbox(self, ids: list[int]) -> None: ...


@runtime_checkable
class IncidentMemory(Protocol):
    """Long-term memory of resolved incidents, recalled by service."""

    def recall(self, services: list[str], ttl_days: int, limit: int = 3) -> list[dict]: ...

    def add_memory(self, service: str, run_id: str, content: dict) -> None: ...


@runtime_checkable
class StoreHealth(Protocol):
    """Probe and counter queries for health checks and metrics."""

    def ping(self) -> bool: ...

    def status_counts(self) -> dict[str, int]: ...

    def event_counts(self) -> dict[str, int]: ...


@runtime_checkable
class RunStorePort(RunRepository, EventLog, OperatorInbox, IncidentMemory, StoreHealth, Protocol):
    """Everything the SQLite ``Store`` offers. Collaborators depend on the narrow roles above."""
