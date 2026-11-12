"""Composition root: the one place that picks concrete adapters and wires the object graph.

Everything else receives its collaborators through constructors (Dependency
Injection without a framework, as in Cosmic Python's ``bootstrap``). Tests,
evals, and the HTTP app all build the service through ``build_run_service``.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

from app.application.agent_steps import AgentSteps
from app.application.events import RunEventRecorder
from app.application.gate_resolver import GateResolver
from app.application.graph_runner import GraphRunner
from app.application.llm_gateway import LLMGateway
from app.application.ports import TelemetryPort
from app.application.run_controls import RunControls
from app.application.run_queries import RunQueries
from app.application.run_service import RunService
from app.application.tool_dispatch import ToolCallDispatcher
from app.application.tool_executor import ToolExecutor
from app.application.tools import TOOLS, tool_schemas
from app.application.write_gate import WriteGate
from app.core.config import Settings
from app.domain.ports import ClusterPort, LLMPort, RunStorePort
from app.infrastructure.cluster.factory import cluster_for_run
from app.infrastructure.cluster.mock_cluster import list_scenarios, load_scenario
from app.infrastructure.llm import make_llm
from app.infrastructure.observability.langfuse_tracer import configure_langfuse, shutdown_langfuse
from app.infrastructure.observability.logging_setup import configure_logging
from app.infrastructure.observability.telemetry import PrometheusOtelTelemetry
from app.infrastructure.observability.tracing import configure_tracing, shutdown_tracing
from app.infrastructure.persistence.checkpointer import open_checkpointer
from app.infrastructure.persistence.store import Store
from app.presentation.views.decisions import enrich_pending
from app.presentation.views.tool_labels import present_tool

log = logging.getLogger("api")


def _cluster_for(st: dict) -> ClusterPort:
    """Bind the platform adapter to one run's scenario and environment checkpoint."""
    return cluster_for_run(st["scenario_id"], st["env"])


def _build_agent_steps(
    store: RunStorePort,
    llm: LLMPort,
    settings: Settings,
    events: RunEventRecorder,
    controls: RunControls,
    telemetry: TelemetryPort,
) -> AgentSteps:
    """Wire the per-step facade: LLM gateway, tool dispatch and gate resolution."""
    executor = ToolExecutor(settings, events, telemetry)
    dispatcher = ToolCallDispatcher(
        tools=TOOLS,
        executor=executor,
        write_gate=WriteGate(
            min_write_confidence=settings.min_write_confidence, events=events, present_pending=enrich_pending
        ),
        events=events,
        cluster_for=_cluster_for,
        present_tool=present_tool,
        max_identical_calls=settings.max_identical_tool_calls,
    )
    gates = GateResolver(
        tools=TOOLS,
        runs=store,
        events=events,
        executor=executor,
        cluster_for=_cluster_for,
        present_tool=present_tool,
        telemetry=telemetry,
    )
    return AgentSteps(
        runs=store,
        inbox=store,
        memory=store,
        settings=settings,
        events=events,
        llm=LLMGateway(llm, settings, events, tool_schemas(), telemetry),
        dispatcher=dispatcher,
        gates=gates,
        controls=controls,
        cluster_for=_cluster_for,
    )


def build_run_service(
    store: RunStorePort,
    llm: LLMPort,
    settings: Settings,
    *,
    telemetry: TelemetryPort | None = None,
) -> RunService:
    """Wire ``RunService`` and its collaborators with the default adapters."""
    telemetry = telemetry or PrometheusOtelTelemetry()
    events = RunEventRecorder(store, store)
    controls = RunControls()
    steps = _build_agent_steps(store, llm, settings, events, controls, telemetry)
    runner = GraphRunner(
        runs=store,
        events=events,
        steps=steps,
        controls=controls,
        settings=settings,
        checkpointer_factory=open_checkpointer,
        present_pending=enrich_pending,
    )
    queries = RunQueries(
        store=store, llm=llm, runner=runner, scenario_loader=load_scenario, scenario_catalog=list_scenarios
    )
    return RunService(
        store=store,
        settings=settings,
        events=events,
        runner=runner,
        steps=steps,
        controls=controls,
        tools=TOOLS,
        queries=queries,
        scenario_loader=load_scenario,
    )


@dataclass
class Container:
    """Process-wide singletons for the HTTP app plus their start / stop hooks."""

    settings: Settings
    llm: LLMPort
    service: RunService
    telemetry: TelemetryPort = field(default_factory=PrometheusOtelTelemetry)

    @property
    def queries(self) -> RunQueries:
        """Read side of the run lifecycle (shares the service's Store and runner)."""
        return self.service.queries

    async def start(self) -> None:
        """Tracing exporters, crash recovery, and startup warnings."""
        s = self.settings
        configure_tracing(s.otlp_endpoint)
        configure_langfuse(s.langfuse_public_key, s.langfuse_secret_key, s.langfuse_host)
        n = self.service.recover()
        if n:
            log.warning("marked %d in-flight run(s) as interrupted after restart", n)
        if not s.api_token:
            log.warning(
                "API_TOKEN is not set: the API, including production approvals, is unauthenticated. "
                "Set API_TOKEN before exposing this service beyond localhost."
            )
        log.info("ready: provider=%s model=%s", self.llm.provider, self.llm.model)

    async def aclose(self) -> None:
        """Stop runs, release the LLM client's connection pool, flush exporters."""
        await self.service.shutdown()
        close = getattr(self.llm, "aclose", None)
        if close is not None:
            try:
                await close()
            except Exception:  # noqa: BLE001 - shutdown must finish even if a pool is already closed
                log.debug("LLM client close failed", exc_info=True)
        shutdown_langfuse()
        shutdown_tracing()


def build_container(settings: Settings | None = None, llm: LLMPort | None = None) -> Container:
    """Settings from the environment, SQLite Store, configured LLM Strategy, wired service."""
    settings = settings or Settings.from_env()
    configure_logging(settings.log_format, settings.log_level)
    llm = llm or make_llm(settings)
    telemetry = PrometheusOtelTelemetry()
    service = build_run_service(Store(settings.db_path), llm, settings, telemetry=telemetry)
    return Container(settings=settings, llm=llm, service=service, telemetry=telemetry)
