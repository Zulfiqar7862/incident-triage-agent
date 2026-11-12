"""Read side of the run lifecycle (CQRS-lite): lookups, listings, audit verification, health."""

from __future__ import annotations

from app.application.exceptions import NotFound
from app.application.graph_runner import GraphRunner
from app.application.ports import ScenarioCatalog, ScenarioLoader
from app.domain.ports import LLMPort, RunStorePort


class RunQueries:
    """Side-effect-free queries used by the HTTP layer and the run view."""

    def __init__(
        self,
        *,
        store: RunStorePort,
        llm: LLMPort,
        runner: GraphRunner,
        scenario_loader: ScenarioLoader,
        scenario_catalog: ScenarioCatalog = list,
    ) -> None:
        self._store = store
        self._llm = llm
        self._runner = runner
        self._load_scenario = scenario_loader
        self._scenario_catalog = scenario_catalog

    @property
    def model_info(self) -> dict[str, str]:
        """Provider and model name of the configured LLM Strategy."""
        return {"provider": self._llm.provider, "model": self._llm.model}

    def get(self, run_id: str) -> dict:
        st = self._store.load(run_id)
        if st is None:
            raise NotFound(f"Run '{run_id}' not found")
        return st

    def find(self, run_id: str) -> dict | None:
        """Like ``get`` but returns ``None`` for an unknown run (SSE polling)."""
        return self._store.load(run_id)

    def is_active(self, run_id: str) -> bool:
        """True while a task is driving the run (not merely unwinding after it parked)."""
        if not self._runner.has_live_task(run_id):
            return False
        st = self._store.load(run_id)
        return not (st and st["status"] not in ("running", "queued"))

    def scenario_alert(self, scenario_id: str) -> dict | None:
        """Alert of a scenario, for checkpoints written before ``alert`` was stored."""
        try:
            return self._load_scenario(scenario_id)["alert"]
        except Exception:  # noqa: BLE001 - a missing or malformed scenario file just means "no alert"
            return None

    def list_scenarios(self) -> list[dict]:
        return self._scenario_catalog()

    def list_runs(self) -> list[dict]:
        return self._store.list_runs()

    def events_since(self, run_id: str, after: int = 0) -> list[dict]:
        return self._store.events_since(run_id, after)

    def verify_events(self, run_id: str) -> dict:
        """Recompute the run's hash chain; ``NotFound`` for an unknown run."""
        self.get(run_id)
        return self._store.verify_event_chain(run_id)

    def health_counts(self) -> tuple[dict[str, int], dict[str, int]]:
        return self._store.status_counts(), self._store.event_counts()

    def ping(self) -> bool:
        return self._store.ping()
