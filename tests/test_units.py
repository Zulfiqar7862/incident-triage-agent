"""Fast unit tests for the application collaborators, using in-memory fakes (no SQLite, no LangGraph)."""

from __future__ import annotations

from typing import Any

import pytest
from app.application.events import RunEventRecorder
from app.application.ports import NullTelemetry, TelemetryPort, no_tool_labels
from app.application.tool_dispatch import ToolCallDispatcher
from app.application.tool_executor import ToolExecutor
from app.application.tools import TOOLS
from app.application.write_gate import WriteGate
from app.core.config import ConfigError, Settings
from app.domain.errors import ToolError
from app.domain.llm import ToolCall
from app.infrastructure.llm.factory import PROVIDERS, resolve_provider


class FakeEventLog:
    """In-memory ``EventLog``."""

    def __init__(self) -> None:
        self.events: list[tuple[str, str, dict[str, Any]]] = []

    def append_event(self, run_id: str, type_: str, payload: dict[str, Any]) -> dict:
        self.events.append((run_id, type_, payload))
        return {"seq": len(self.events)}

    def events_since(self, run_id: str, after: int = 0, limit: int = 500) -> list[dict]:
        return []

    def verify_event_chain(self, run_id: str) -> dict[str, Any]:
        return {"ok": True, "events": len(self.events)}

    def types(self) -> list[str]:
        return [t for _, t, _ in self.events]


class FakeRuns:
    """In-memory ``RunRepository``: remembers the last saved state."""

    def __init__(self) -> None:
        self.saved: list[dict] = []

    def load(self, run_id: str) -> dict | None:
        return self.saved[-1] if self.saved else None

    def save(self, state: dict, *, cas: bool = True) -> None:
        self.saved.append(dict(state))

    def create_run(self, state: dict) -> None:
        self.saved.append(dict(state))

    def list_runs(self, limit: int = 50) -> list[dict]:
        return []

    def runs_with_status(self, statuses: list[str]) -> list[dict]:
        return []


def _known(name: str) -> object:
    if name != "checkout":
        raise ToolError(f"Unknown service '{name}'")
    return name


@pytest.fixture
def log() -> FakeEventLog:
    return FakeEventLog()


@pytest.fixture
def recorder(log: FakeEventLog) -> RunEventRecorder:
    return RunEventRecorder(log, FakeRuns())


@pytest.fixture
def st() -> dict:
    return {"run_id": "run-1", "step": 3, "status": "running"}


def _rollback(confidence: float, service: str = "checkout") -> ToolCall:
    return ToolCall(
        "c1", "rollback_deploy", {"service": service, "to_version": "v1", "reason": "bad", "confidence": confidence}
    )


def test_event_recorder_stamps_step_and_persists_status(log, st):
    runs = FakeRuns()
    rec = RunEventRecorder(log, runs)
    rec.set_status(st, "paused", "operator")
    assert runs.saved[-1]["status"] == "paused"
    assert log.events[-1][1] == "run.status" and log.events[-1][2]["step"] == 3


def test_write_gate_opens_an_approval_above_the_floor(recorder, st):
    gate = WriteGate(min_write_confidence=0.5, events=recorder)
    pending = gate.open(st, _rollback(0.9), TOOLS["rollback_deploy"], 3, _known)
    assert isinstance(pending, dict) and pending["kind"] == "approval" and pending["executing"] is False


def test_write_gate_bounces_low_confidence_without_paging_a_human(recorder, log, st):
    gate = WriteGate(min_write_confidence=0.5, events=recorder)
    outcome = gate.open(st, _rollback(0.2), TOOLS["rollback_deploy"], 3, _known)
    assert isinstance(outcome, tuple) and outcome[1] is True
    assert log.types() == ["policy.blocked"]


def test_write_gate_blocks_unknown_services(recorder, log, st):
    gate = WriteGate(min_write_confidence=0.5, events=recorder)
    outcome = gate.open(st, _rollback(0.9, service="nope"), TOOLS["rollback_deploy"], 3, _known)
    assert isinstance(outcome, tuple) and "Unknown service" in outcome[0]
    assert log.events[-1][2]["reason"] == "unknown_service"


def test_write_gate_turns_ask_operator_into_an_input_gate(recorder, st):
    gate = WriteGate(min_write_confidence=0.5, events=recorder)
    pending = gate.open(
        st, ToolCall("q1", "ask_operator", {"question": "Roll back?"}), TOOLS["ask_operator"], 3, _known
    )
    assert isinstance(pending, dict) and pending["kind"] == "input" and pending["question"] == "Roll back?"


def _dispatcher(recorder: RunEventRecorder) -> ToolCallDispatcher:
    settings = Settings()
    return ToolCallDispatcher(
        tools=TOOLS,
        executor=ToolExecutor(settings, recorder, NullTelemetry()),
        write_gate=WriteGate(min_write_confidence=0.5, events=recorder),
        events=recorder,
        cluster_for=lambda st: None,  # type: ignore[arg-type,return-value]
        present_tool=no_tool_labels,
        max_identical_calls=3,
    )


def test_dispatcher_prefers_a_name_handler_over_the_kind_handler(recorder):
    d = _dispatcher(recorder)
    seen: list[str] = []
    d.register("get_alert", lambda batch, call, spec: seen.append(call.name))
    d.handler_for(TOOLS["get_alert"])(None, ToolCall("x", "get_alert", {}), TOOLS["get_alert"])  # type: ignore[arg-type]
    assert seen == ["get_alert"]
    assert d.handler_for(TOOLS["list_services"]) is not d.handler_for(TOOLS["get_alert"])


def test_dispatcher_raises_for_an_unregistered_kind(recorder):
    d = _dispatcher(recorder)
    d._handlers.clear()
    with pytest.raises(LookupError):
        d.handler_for(TOOLS["get_alert"])


def test_null_telemetry_is_a_drop_in_telemetry_port():
    t = NullTelemetry()
    assert isinstance(t, TelemetryPort)
    with t.span("llm", model="m") as attrs:
        assert attrs == {"model": "m"}
    assert t.export({}, {})[0] == b""


def test_provider_auto_falls_back_to_scripted_without_keys(monkeypatch):
    for k in ("GEMINI_API_KEY", "GOOGLE_API_KEY", "ANTHROPIC_API_KEY", "OPENAI_API_KEY"):
        monkeypatch.delenv(k, raising=False)
    assert resolve_provider(Settings(llm_provider="auto", require_llm=False)) == "scripted"
    with pytest.raises(ConfigError):
        resolve_provider(Settings(llm_provider="auto", require_llm=True))
    assert set(PROVIDERS) == {"gemini", "anthropic", "openai", "scripted"}
