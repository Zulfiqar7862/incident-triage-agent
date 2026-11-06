"""Outbound ports (Protocols) for infrastructure adapters.

Runtime and application services depend on these abstractions; Store, MockCluster,
and LLM providers implement them. Keeps DI explicit without a DI framework.
"""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable


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
    ) -> Any: ...


@runtime_checkable
class ClusterPort(Protocol):
    """Adapter surface for MockCluster today; live K8s/Prometheus later."""

    def resolved(self) -> bool: ...

    def _svc(self, name: str) -> dict: ...


@runtime_checkable
class RunStorePort(Protocol):
    """Subset of Store used by run lifecycle / SSE."""

    def load(self, run_id: str) -> dict | None: ...

    def save(self, state: dict) -> None: ...

    def create_run(self, state: dict) -> None: ...

    def append_event(self, run_id: str, type_: str, payload: dict) -> dict: ...

    def list_runs(self, limit: int = 100) -> list[dict]: ...

    def runs_with_status(self, statuses: list[str]) -> list[dict]: ...

    def recall(self, services: list[str], ttl_days: int, limit: int) -> list[dict]: ...

    def add_memory(self, service: str, run_id: str, content: dict) -> None: ...

    def push_inbox(self, run_id: str, text: str) -> None: ...
