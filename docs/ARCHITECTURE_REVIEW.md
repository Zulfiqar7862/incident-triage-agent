# Architecture review guide

A reviewer's map: where each concern lives, what a strict review found and how
it was fixed, and which test proves each claim. Design detail is in the
[HLD](HLD.md), [LLD](LLD.md) and [ADRs](adr/README.md).

## 1. Where things live

```text
app/domain/          Ports (Protocols), policies, value types. Standard library only.
app/application/     Use cases: RunService, RunQueries, GraphRunner, AgentSteps,
                     ToolCallDispatcher, WriteGate, GateResolver, LLMGateway, ToolExecutor;
                     agent/ (LangGraph graph and nodes), tools/, context/
app/infrastructure/  Adapters: persistence/ (Store, checkpointer, Alembic), cluster/
                     (MockCluster), llm/ (one module per provider + registry), observability/
app/presentation/    http/ (FastAPI app, routes, dependencies) and views/ (operator projections)
app/core/            config.py (Settings) and container.py (composition root)
app/main.py          Entrypoint: create_app() and app
frontend/src/        app/ → features/{run,approval} → components, hooks, lib, stores, types
```

## 2. Review findings and fixes

A staff-level review of commit `bbb53aa` found 22 issues: 3 critical, 6 high,
8 medium, 5 low.

| # | Severity | Finding | Fix |
| --- | --- | --- | --- |
| 1 | Critical | Eight top-level packages (`app/agent`, `app/llm`, `app/runtime.py`, ...) sat outside the layers | Every module now lives in `domain`, `application`, `infrastructure`, `presentation` or `core`; enforced by `test_every_backend_module_lives_in_a_named_layer` |
| 2 | Critical | `RunService` was a 552-line god class | Split into [`RunService`](../app/application/run_service.py#L32), [`RunQueries`](../app/application/run_queries.py#L11), [`GraphRunner`](../app/application/graph_runner.py#L30), [`AgentSteps`](../app/application/agent_steps.py#L28) |
| 3 | Critical | `act_node` (174 lines) chose behaviour with an if/elif chain on tool kind | [`ToolCallDispatcher`](../app/application/tool_dispatch.py#L47) handler registry; [`act_node`](../app/application/agent/nodes/act.py#L12) is now ~20 lines |
| 4 | High | `approval_node` (163 lines) held business rules | [`GateResolver`](../app/application/gate_resolver.py#L28); the node only interrupts and delegates |
| 5 | High | Nodes reached through the port to `rt.store` | Step port has explicit `save`, `drain_inbox`, `ack_inbox`; `test_graph_nodes_see_only_the_step_port` |
| 6 | High | Silent `except Exception: pass` around metrics; function-local imports | Metrics go through [`TelemetryPort`](../app/application/ports.py#L57); `test_no_function_local_imports_of_app_modules` |
| 7 | High | `providers.py` (457 lines) with an if-chain `make_llm` | One module per adapter; [`PROVIDERS`](../app/infrastructure/llm/factory.py#L61) registry |
| 8 | High | Operator wording (`tools/display.py`) pulled into the application layer | Moved to `presentation/views/tool_labels.py` and injected as a `ToolPresenter` |
| 9 | High | Wide `AgentRuntimePort` (14 members) | Narrow [`AgentStepsPort`](../app/application/ports.py#L94); `RunStorePort` split into five role ports |
| 10 | Medium | `llm_factory.py` re-export shim | Deleted |
| 11 | Medium | `create_app` mixed wiring, lifespan and static files | [`container.py`](../app/core/container.py#L171) wires; [`http/app.py`](../app/presentation/http/app.py#L66) builds FastAPI; `main.py` is the entrypoint |
| 12 | Medium | Per-run `threading.Lock` dict inside the service | Encapsulated in [`GateLocks`](../app/application/run_controls.py#L31) with the trade-off documented |
| 13 | Medium | Frontend shared code imported features | `app → features → shared`; Vitest boundary test |
| 14 | Medium | Barrel files and a cross-feature import | Barrels removed; approval composed into the sidebar at the app layer |
| 15 | Medium | Components of 239–319 lines mixing state and markup; `ToolOutputView` (319 lines) was dead code | Split into small components and `useApprovalForm`; `ToolOutputView` deleted; 200-line limit tested |
| 16 | Medium | Docs had no requirements, estimates, alternatives or ADRs | HLD and LLD rewritten (arc42, C4); six ADRs |
| 17 | Medium | `build_gate_or_block` free function with many parameters | [`WriteGate`](../app/application/write_gate.py#L19) with constructor-injected collaborators |
| 18 | Low | `ScriptedPolicy.decide` is 149 lines | Accepted: deterministic test double; exempt from the size budget ([ADR-0004](adr/0004-deterministic-scripted-llm-provider.md)) |
| 19 | Low | `event_display` if-chain | [`EVENT_VIEWS`](../app/presentation/views/events.py#L95) registry |
| 20 | Low | Broad `except` in `readyz` / `metrics` | Kept on purpose: probes must not raise; commented |
| 21 | Low | Missing return types on public functions | Added; mypy clean |
| 22 | Low | No fast unit tests with fakes | [`tests/test_units.py`](../tests/test_units.py): `WriteGate`, `ToolCallDispatcher`, `NullTelemetry`, provider registry |

Size after the refactor: no backend file over 300 lines, no function over 60,
no class over 250 (the scripted provider is the one exemption).

## 3. Patterns and SOLID

The pattern table with links is in [LLD §13](LLD.md#13-design-patterns) and
the SOLID mapping in [LLD §14](LLD.md#14-solid). Short version:

| Principle | Concrete change |
| --- | --- |
| S | `RunService` split four ways; `LLMGateway` owns retries and accounting; `GateResolver` owns decisions |
| O | Registries for tool handlers, providers, event views and prompt sections |
| L | Every LLM adapter, `GeminiWithFallback`, `NullTelemetry` and test fakes are used only through Protocols |
| I | `RunStorePort` = five role ports; nodes see only `AgentStepsPort` |
| D | Application classes take ports in constructors; only `core/container.py` names concrete classes |

## 4. Claim → code → proof

| Claim | Code | Verified by |
| --- | --- | --- |
| Domain is framework-free | `app/domain/` | `test_domain_is_pure_python` |
| Use cases depend on ports, not adapters | `app/application/` | `test_application_depends_on_ports_not_adapters` |
| Adapters do not depend on the web layer | `app/infrastructure/` | `test_infrastructure_does_not_depend_on_presentation_or_core_wiring` |
| Routes reach storage only through the application | `app/presentation/` | `test_presentation_uses_application_not_adapters` |
| Every adapter satisfies its port | `Store`, `MockCluster`, LLM adapters, telemetry | `test_adapters_implement_ports`, `test_agent_steps_satisfies_the_step_port` |
| Every tool and provider is registered | `ToolCallDispatcher`, `PROVIDERS` | `test_every_tool_has_a_dispatch_handler`, `test_provider_registry_covers_every_configurable_provider` |
| Gemini falls back only on quota errors | `GeminiWithFallback` | `test_quota_error_switches_to_fallback_model` |
| No production change without approval | `WriteGate`, `approval_node`, `GateResolver` | `test_bad_deploy_is_rolled_back_after_approval`, `test_rejection_is_fed_back_and_nothing_is_executed`, `test_interrupt_resume_reject` |
| Operator can edit before approving | `RunService.approve` | `test_operator_can_edit_arguments_before_approving` |
| Low-confidence writes never reach a human | `evaluate_write_confidence`, `WriteGate` | `test_low_confidence_write_is_bounced_back_to_the_agent`, `test_write_gate_bounces_low_confidence_without_paging_a_human` |
| Unknown services are blocked | `WriteGate` | `test_unknown_service_write_is_blocked_before_approval`, `test_write_gate_blocks_unknown_services` |
| Durable resume after a crash, including mid-approval | `RunService.recover`, `resume`, idempotent writes | `test_run_survives_a_crash_and_resumes_from_checkpoint`, `test_approval_survives_restart_and_is_idempotent`, `test_mid_approval_crash_does_not_duplicate_tool_result`, `test_graceful_shutdown_marks_runs_interrupted` |
| Pause, resume, emergency stop | `RunService` | `test_pause_and_resume`, `test_emergency_stop_cancels_active_runs`, `test_emergency_stop_and_verify_http` |
| Budgets and loop guard stop runaway runs | `exhausted_budget`, `LoopGuard` | `test_step_budget_stops_runaway_loops`, `test_hard_budget_stop_cancels`, `test_budget_alert_emitted_before_hard_stop`, `test_loop_guard_stops_identical_retries` |
| Audit log is hash-chained and detects edits | `Store.append_event`, `verify_event_chain` | `test_event_hash_chain_verifies_and_detects_tamper` |
| Prompt injection in tool output is flagged, not followed | `ToolExecutor.record` | `test_injection_in_logs_is_flagged_and_not_executed`, eval `cache-oom-injection` |
| Every tool result is counted in Prometheus | `ToolExecutor` → `TelemetryPort.tool_call` | `test_tool_calls_are_counted_in_prometheus` |
| Operator view never shows raw code or logs | `app/presentation/views/` | `tests/test_display.py` (6 tests), `scripts/e2e_ui.py` |
| API auth, headers, limits, 429 | `app/presentation/http/` | `tests/test_production.py` |
| Agent resolves the scenarios | whole system | `python -m evals.run_evals --provider scripted` (3/3) |
| UI works end to end in a browser | frontend + API | `python -m scripts.e2e_ui` |

## 5. Known gaps

- The platform is simulated (`MockCluster`); no live cluster adapter exists.
- The Store is SQLite only; `DATABASE_URL` moves only the LangGraph checkpointer to Postgres.
- One process, one worker; no distributed run leases ([ADR-0005](adr/0005-single-worker-process-model.md)).
- The Langfuse client is configured but generations are not sent yet.
- Emergency stop is available through the API, not as a console button.
- Operator identity (`X-Operator`) is self-declared.

## 6. Run the proof yourself

```bash
.venv/bin/pytest -q tests/test_architecture.py tests/test_units.py
TOOL_BACKOFF_S=0.01 .venv/bin/pytest -q -m 'not live'
.venv/bin/ruff check app tests evals scripts && .venv/bin/ruff format --check app tests evals scripts && .venv/bin/mypy app
TOOL_BACKOFF_S=0.01 .venv/bin/python -m evals.run_evals --provider scripted
(cd frontend && npm run lint && npm run format:check && npm run typecheck && npm test && npm run build)
TOOL_BACKOFF_S=0.01 SCRIPTED_DELAY_S=0.12 .venv/bin/python -m scripts.e2e_ui
```

In PyCharm the same checks are the shared run configurations
**Architecture tests** and **Tests (pytest)** (see [PYCHARM_DEMO.md](PYCHARM_DEMO.md)).
CI runs them on every push ([`.github/workflows/ci.yml`](../.github/workflows/ci.yml)).
