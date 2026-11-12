"""Outbound ports (Protocols) implemented by infrastructure adapters.

The application layer (``app.application``, ``app.agent``) depends only on
these abstractions. Concrete adapters: ``app.infrastructure.store.Store``
(RunStorePort), ``app.infrastructure.mock_cluster.MockCluster`` (ClusterPort),
and the providers in ``app.llm`` (LLMPort). No DI framework: adapters are
passed to constructors by the composition roots (``app.runtime``, ``app.main``).
"""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable

from app.domain.llm import LLMResponse


@runtime_checkable
class LLMPort(Protocol):
    """Strategy surface shared by Gemini / Anthropic / OpenAI / scripted providers."""

    provider: str
    model: str

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
class RunStorePort(Protocol):
    """Durable run checkpoints, append-only event log, operator inbox, long-term memory."""

    def load(self, run_id: str) -> dict | None: ...

    def save(self, state: dict, *, cas: bool = True) -> None: ...

    def create_run(self, state: dict) -> None: ...

    def append_event(self, run_id: str, type_: str, payload: dict[str, Any]) -> dict: ...

    def events_since(self, run_id: str, after: int = 0, limit: int = 500) -> list[dict]: ...

    def verify_event_chain(self, run_id: str) -> dict[str, Any]: ...

    def list_runs(self, limit: int = 50) -> list[dict]: ...

    def runs_with_status(self, statuses: list[str]) -> list[dict]: ...

    def push_inbox(self, run_id: str, text: str) -> None: ...

    def peek_inbox(self, run_id: str) -> list[dict]: ...

    def ack_inbox(self, ids: list[int]) -> None: ...

    def recall(self, services: list[str], ttl_days: int, limit: int = 3) -> list[dict]: ...

    def add_memory(self, service: str, run_id: str, content: dict) -> None: ...

    def ping(self) -> bool: ...

    def status_counts(self) -> dict[str, int]: ...

    def event_counts(self) -> dict[str, int]: ...
