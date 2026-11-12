"""Composition of the run service with its default adapters.

``RunService`` (application layer) receives every adapter through its
constructor. ``Runtime`` is the one place that chooses the concrete ones:
SQLite ``Store``, simulated ``MockCluster``, LangGraph checkpointer, scenario
files, and the operator presenter for pending decisions. Tests, evals, and
``app.main.create_app`` construct ``Runtime(store, llm, settings)``.
"""

from __future__ import annotations

from app.application.exceptions import InvalidInput, NotFound, RunStateError, TooBusy
from app.application.run_service import RunService
from app.config import Settings
from app.domain.lifecycle import NUDGE, RESUMABLE, TERMINAL
from app.domain.ports import LLMPort, RunStorePort
from app.infrastructure.checkpointer import open_checkpointer
from app.infrastructure.cluster import cluster_for_run
from app.infrastructure.mock_cluster import list_scenarios, load_scenario
from app.presentation.operator import enrich_pending

__all__ = [
    "Runtime",
    "RunService",
    "NotFound",
    "RunStateError",
    "InvalidInput",
    "TooBusy",
    "TERMINAL",
    "RESUMABLE",
    "NUDGE",
]


class Runtime(RunService):
    """``RunService`` wired with the default infrastructure adapters."""

    def __init__(self, store: RunStorePort, llm: LLMPort, settings: Settings):
        super().__init__(
            store,
            llm,
            settings,
            cluster_factory=cluster_for_run,
            checkpointer_factory=open_checkpointer,
            scenario_loader=load_scenario,
            present_pending=enrich_pending,
            scenario_catalog=list_scenarios,
        )
