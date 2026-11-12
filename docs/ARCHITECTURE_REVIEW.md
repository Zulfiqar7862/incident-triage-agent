# Architecture Review Guide

For reviewers: each claim below points to the code that implements it and to the
automated check that proves it. Run every check locally with the commands in
[section 6](#6-run-the-proof-yourself). Design context: [HLD](HLD.md), [LLD](LLD.md).

Line anchors match the current `main`; if code moves, file paths and symbol names
are the stable reference.

## 1. Project structure and responsibilities

```text
app/domain/          Pure policy and contracts (ports, write gate decision, budgets, guards, lifecycle, LLM value types)
app/application/     Use cases (RunService) and their collaborators (events, LLM gateway, tool executor, write gate)
app/agent/           LangGraph graph and nodes; call the service only through AgentRuntimePort
app/tools/           Tool catalog: typed argument models, JSON schemas, read / write / meta kinds
app/context/         Prompt and context-window construction
app/infrastructure/  Adapters: SQLite Store, MockCluster, runbooks, LangGraph checkpointer, factories
app/llm/             LLM adapters: Gemini (+ fallback), Anthropic, OpenAI, scripted
app/presentation/    FastAPI routes, schemas, auth, error mapping, middleware; operator projections
app/observability/   Logging, tracing, metrics, Langfuse client
app/config/          Settings
app/runtime.py       Composition: RunService + default adapters
app/main.py          HTTP composition root
frontend/src/        features/ (run, approval) · components/ · lib/ · store/ · pages/
tests/               pytest, including test_architecture.py
```

### What changed in the restructuring (before → after)

| Before | After | Why |
| --- | --- | --- |
| `app/runtime.py` (≈700 lines: lifecycle, drive loop, LLM retry, tool retry, recording, budgets, API view) | [`app/application/run_service.py`](../app/application/run_service.py) + [`events.py`](../app/application/events.py), [`llm_gateway.py`](../app/application/llm_gateway.py), [`tool_executor.py`](../app/application/tool_executor.py), [`working_memory.py`](../app/application/working_memory.py), [`domain/budget.py`](../app/domain/budget.py); `app/runtime.py` is a 50-line composition | Single responsibility per class; testable seams |
| `app/main.py` (≈370 lines: wiring + all routes + auth + errors + middleware) | [`app/presentation/http/`](../app/presentation/http) (`routes.py`, `schemas.py`, `dependencies.py`, `errors.py`, `middleware.py`); `app/main.py` wires and mounts | Thin presentation; routes call one service method |
| `app/store.py`, `app/mock_env.py`, `app/runbooks.py`, `app/agent/checkpointer.py` | `app/infrastructure/store.py`, `mock_cluster.py`, `runbooks.py`, `checkpointer.py` | Adapters live in one layer |
| `app/guards.py`, `app/memory/working.py`, LLM value types in `app/llm/providers.py`, tool errors in `app/mock_env.py` | `app/domain/guards.py`, `memory.py`, `llm.py`, `errors.py` | Pure policy and shared types belong to the domain |
| `app/scripted.py`, `app/logging_setup.py` | `app/llm/scripted.py`, `app/observability/logging_setup.py` | Grouped with their peers |
| Graph nodes called private runtime methods (`rt._emit`, `rt._gate`, `rt._control.pop`, …) | Nodes call the public [`AgentRuntimePort`](../app/application/ports.py#L27) (`emit`, `gate`, `take_control`, …) | Depend on an interface, not internals |
| `ClusterPort` had `_svc` only; `RunStorePort` covered half the Store | Ports list every method the application uses; `MockCluster.validate_service` replaces `_svc` access | Complete, honest contracts |
| Runtime built the public run view (application → presentation dependency) | [`app/presentation/run_view.py`](../app/presentation/run_view.py) `present_run` | Dependency rule |
| `enrich_pending` / `present_report` in `app/tools/display.py` imported presentation | Moved to [`app/presentation/operator.py`](../app/presentation/operator.py); injected into `RunService` as `present_pending` | Dependency rule |
| `NUDGE` and tool-output formatting duplicated | One copy each (`app/domain/lifecycle.py`, `format_tool_output`) | DRY |
| Frontend: query keys as string literals in five files; start-run mutation written twice; SSE hook and approval card outside their features | [`lib/queryKeys.ts`](../frontend/src/lib/queryKeys.ts), [`features/run/hooks/queries.ts`](../frontend/src/features/run/hooks/queries.ts), [`useStartRun.ts`](../frontend/src/features/run/hooks/useStartRun.ts), `features/run/hooks/useRunStream.ts`, `features/approval/ApprovalCard.tsx` | Feature folders; one source of truth for cache keys |

API routes, request/response shapes, event types and payloads, tool names, and
approval semantics did not change; the full test suite and the browser E2E run
unchanged against the new structure.

## 2. Design patterns in the code

Only patterns that exist in the code are listed.

| Pattern | Where | Why |
| --- | --- | --- |
| Ports and adapters (hexagonal) | Ports: [`app/domain/ports.py`](../app/domain/ports.py). Adapters: [`Store`](../app/infrastructure/store.py#L62), [`MockCluster`](../app/infrastructure/mock_cluster.py#L61), [`app/llm/providers.py`](../app/llm/providers.py) | Swap storage, platform, or model without touching use cases |
| Strategy | `LLMPort` implemented by `GeminiLLM`, `GeminiWithFallback`, `AnthropicLLM`, `OpenAILLM`, `ScriptedPolicy`; chosen by [`make_llm`](../app/llm/providers.py#L421) | Live and offline models are interchangeable at runtime |
| Factory | [`make_llm`](../app/llm/providers.py#L421), [`cluster_for_run`](../app/infrastructure/cluster.py#L9), [`open_checkpointer`](../app/infrastructure/checkpointer.py#L14), [`new_run_state`](../app/agent/state.py) | Creation logic in one place; callers get a port |
| Adapter | `MockCluster` adapts scenario JSON to `ClusterPort`; `to_gemini` / `to_anthropic` / `to_openai` translate the neutral message history to each wire format ([`providers.py#L89`](../app/llm/providers.py#L89)) | One internal model, many external formats |
| Decorator | [`GeminiWithFallback`](../app/llm/providers.py#L343) wraps a `GeminiLLM` with the same interface and adds quota fallback; [`LLMGateway`](../app/application/llm_gateway.py) wraps any `LLMPort` with retries and tracing | Add behaviour without changing the wrapped class |
| Dependency injection / composition root | [`RunService.__init__`](../app/application/run_service.py#L59) takes ports and factories; [`Runtime`](../app/runtime.py#L35) and [`create_app`](../app/main.py#L45) choose adapters; routes get the service via FastAPI `Depends(get_runtime)` ([`dependencies.py`](../app/presentation/http/dependencies.py#L14)) | No global singletons; tests pass fakes |
| Facade | `RunService` exposes `create_run`, `approve`, `pause`, … over the graph, gateway, executor, and recorder | One entry point for presentation |
| Observer (publish / subscribe over a log) | [`RunEventRecorder.emit`](../app/application/events.py#L24) appends to the event log; the SSE route tails it ([`routes.py#L131`](../app/presentation/http/routes.py#L131)); the browser subscribes with `EventSource` ([`useRunStream.ts`](../frontend/src/features/run/hooks/useRunStream.ts)) | Producers and the UI are decoupled; replay from `Last-Event-ID` |
| Registry | [`TOOLS`](../app/tools/specs.py#L215) maps tool name → `ToolSpec` (schema, kind, handler); dispatch by `spec.kind` in `act_node` ([`act.py#L119`](../app/agent/nodes/act.py#L119)) | Add a tool by adding an entry |
| State machine | Run statuses ([`lifecycle.py`](../app/domain/lifecycle.py), [LLD §5](LLD.md#5-run-lifecycle)) and the LangGraph `StateGraph` ([`graph.py`](../app/agent/graph.py)) | Explicit legal transitions; interrupts at human gates |
| Repository with optimistic locking | `Store.save` compare-and-set on `checkpoint_version` ([`store.py#L97`](../app/infrastructure/store.py#L97)) | Detect lost updates between the drive task and operator actions |
| Hash chain | `Store._event_hash` / `verify_event_chain` ([`store.py#L162`](../app/infrastructure/store.py#L162)) | Tamper-evident audit log |
| Reducer (frontend) | [`streamReducer`](../frontend/src/features/run/hooks/useRunStream.ts#L22) | Pure, testable stream state transitions |
| Custom hooks / container–presentational (frontend) | [`useActiveRun`](../frontend/src/features/run/hooks/useActiveRun.ts#L9), [`useRunActions`](../frontend/src/features/run/hooks/useRunActions.ts#L10), [`useStartRun`](../frontend/src/features/run/hooks/useStartRun.ts#L22); components receive data and callbacks | Data fetching and side effects out of components |
| Query key factory (frontend) | [`queryKeys`](../frontend/src/lib/queryKeys.ts#L2) | Reads and invalidations cannot drift apart |

Excerpts:

```python
# app/runtime.py — composition root chooses the adapters (DI, Factory)
class Runtime(RunService):
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
```

```python
# app/infrastructure/cluster.py — Factory returning the port, not the class
def cluster_for_run(scenario_id: str, env: dict) -> ClusterPort:
    return MockCluster(load_scenario(scenario_id), env)
```

```python
# app/application/events.py — the single event publisher (Observer source)
def emit(self, st: dict, type_: str, payload: dict) -> None:
    payload = {"step": st["step"], **payload}
    self._store.append_event(st["run_id"], type_, payload)
```

## 3. SOLID, one example each

**Single responsibility.** Each application class has one reason to change.
`RunEventRecorder` only records events and status;
`ToolExecutor` only runs and records tools; HTTP handlers only translate HTTP.

```python
# app/presentation/http/routes.py#L89 — a route: validate, call one use case, present
@api.post("/runs", status_code=201)
async def create_run(body: CreateRun, actor: str = Depends(require_auth), runtime: Runtime = Depends(get_runtime)):
    st = runtime.create_run(body.scenario_id)
    log.info(json.dumps({"event": "api.run_created", "run": st["run_id"], "actor": actor}))
    return present_run(runtime, st)
```

**Open/closed.** `RunService` is closed for modification but open to new
platforms: a live Kubernetes adapter is a new `ClusterPort` implementation passed
as `cluster_factory`; nothing in the service changes. Error mapping is a table,
so a new application error is one entry:

```python
# app/presentation/http/errors.py#L11
STATUS_BY_ERROR: dict[type[Exception], int] = {
    NotFound: 404,
    RunStateError: 409,
    InvalidInput: 422,
    TooBusy: 429,
    ConcurrencyConflict: 409,
}
```

**Liskov substitution.** Any `LLMPort` works where another is expected.
`GeminiWithFallback` stands in for `GeminiLLM`; tests run the whole agent with
`ScriptedPolicy` or a `FakeLLM` in place of a live provider.

```python
# app/llm/providers.py#L343
class GeminiWithFallback:
    """Primary Gemini model with automatic fallback on 429/quota exhaustion."""
    provider = "gemini"
    def __init__(self, primary: GeminiLLM, fallback: GeminiLLM | None): ...
```

Verified by `test_adapters_implement_domain_ports` and
`test_quota_error_switches_to_fallback_model`.

**Interface segregation.** Clients see only what they need. Graph nodes use
`AgentRuntimePort`; the run view needs two methods, so it declares its own
two-method protocol instead of depending on `RunService`:

```python
# app/presentation/run_view.py#L11
class RunViewSource(Protocol):
    def is_active(self, run_id: str) -> bool: ...
    def scenario_alert(self, scenario_id: str) -> dict | None: ...
```

**Dependency inversion.** The use-case layer depends on abstractions; concrete
adapters are supplied from outside.

```python
# app/application/run_service.py#L59
def __init__(
    self,
    store: RunStorePort,
    llm: LLMPort,
    settings: Settings,
    *,
    cluster_factory: ClusterFactory,
    checkpointer_factory: CheckpointerFactory,
    scenario_loader: ScenarioLoader,
    present_pending: PendingPresenter = dict,
    scenario_catalog: ScenarioCatalog = list,
): ...
```

`test_application_layer_depends_on_ports_not_adapters` fails the build if
`app/application`, `app/agent`, `app/tools`, or `app/context` import an adapter.

## 4. Claim → code → proof

| Claim | Code | Verified by |
| --- | --- | --- |
| Domain is framework-free | `app/domain/` | `tests/test_architecture.py::test_domain_is_pure_python` |
| Use cases depend on ports, not adapters | `app/application/`, `app/agent/`, `app/tools/`, `app/context/` | `test_application_layer_depends_on_ports_not_adapters` |
| Adapters do not depend on the web layer | `app/infrastructure/`, `app/llm/` | `test_infrastructure_does_not_depend_on_presentation` |
| Routes reach storage only through the service | `app/presentation/` | `test_presentation_uses_application_not_adapters` |
| `main.py` is only a composition root | `app/main.py` | `test_routes_are_not_defined_in_the_composition_root` |
| Every adapter satisfies its port | `Store`, `MockCluster`, all LLM providers | `test_adapters_implement_domain_ports`, `test_runtime_satisfies_agent_runtime_port` |
| Gemini fallback only on quota errors | `GeminiWithFallback` | `tests/test_gemini.py::test_quota_error_switches_to_fallback_model` |
| No production change without approval | `write_gate.py`, `approval_node` | `test_bad_deploy_is_rolled_back_after_approval`, `test_rejection_is_fed_back_and_nothing_is_executed`, `test_interrupt_resume_reject` |
| Operator can edit before approving | `RunService.approve` | `test_operator_can_edit_arguments_before_approving` |
| Low-confidence writes never reach a human | `evaluate_write_confidence` | `test_low_confidence_write_is_bounced_back_to_the_agent` |
| Unknown services are blocked | `build_gate_or_block` | `test_unknown_service_write_is_blocked_before_approval` |
| Durable resume after crash, including mid-approval | `RunService.recover`, `resume`, idempotent writes | `test_run_survives_a_crash_and_resumes_from_checkpoint`, `test_approval_survives_restart_and_is_idempotent`, `test_mid_approval_crash_does_not_duplicate_tool_result`, `test_graceful_shutdown_marks_runs_interrupted` |
| Pause / resume / emergency stop | `RunService` | `test_pause_and_resume`, `test_emergency_stop_cancels_active_runs`, `test_emergency_stop_and_verify_http` |
| Budgets and loop guard stop runaway runs | `prepare_node`, `LoopGuard` | `test_step_budget_stops_runaway_loops`, `test_hard_budget_stop_cancels`, `test_budget_alert_emitted_before_hard_stop`, `test_loop_guard_stops_identical_retries` |
| Audit log is hash-chained and detects edits | `Store.append_event`, `verify_event_chain` | `test_event_hash_chain_verifies_and_detects_tamper` |
| Prompt injection in tool output is flagged, not followed | `ToolExecutor.record` | `test_injection_in_logs_is_flagged_and_not_executed`, eval scenario `cache-oom-injection` |
| Every tool result is counted in Prometheus (`agent_tool_calls_total`) | `ToolExecutor.record` | `tests/test_hardening.py::test_tool_calls_are_counted_in_prometheus` |
| Operator view never shows raw code or logs | `app/presentation/operator.py` | `tests/test_display.py` (6 tests), `scripts/e2e_ui.py` |
| API auth, headers, limits, 429 | `app/presentation/http/` | `tests/test_production.py` |
| Agent resolves the scenarios correctly | whole system | `python -m evals.run_evals --provider scripted` (3/3) |
| UI works end to end in a browser | frontend + API | `python -m scripts.e2e_ui` |

## 5. Known gaps (honest list)

- The platform is simulated (`MockCluster`); no live cluster adapter exists yet.
- The Store is SQLite only; `DATABASE_URL` moves only the LangGraph checkpointer to Postgres.
- One process, one worker; no distributed run leases.
- Plain-language tool labels (`present_tool`, [`app/tools/display.py`](../app/tools/display.py))
  live in the tool catalog, next to the tool definitions, because graph nodes
  attach them to `tool.call` events. The module imports only the domain, so the
  layer rules hold; it is a placement choice, not a boundary violation.
- The Langfuse client is configured but generations are not sent yet (OpenTelemetry
  spans and Prometheus metrics are the active telemetry).
- Emergency stop is available through the API, not as a console button.

## 6. Run the proof yourself

```bash
.venv/bin/pytest -q tests/test_architecture.py        # layer boundaries + port conformance
TOOL_BACKOFF_S=0.01 .venv/bin/pytest -q -m 'not live'  # full backend suite
.venv/bin/ruff check app tests evals scripts && .venv/bin/mypy -p app
TOOL_BACKOFF_S=0.01 .venv/bin/python -m evals.run_evals --provider scripted
(cd frontend && npm run lint && npm run typecheck && npm test && npm run build)
TOOL_BACKOFF_S=0.01 SCRIPTED_DELAY_S=0.12 .venv/bin/python -m scripts.e2e_ui
```

In PyCharm the same checks are the shared run configurations
**Architecture tests** and **Tests (pytest)** (see [PYCHARM_DEMO.md](PYCHARM_DEMO.md)).
CI runs them on every push ([`.github/workflows/ci.yml`](../.github/workflows/ci.yml)).
