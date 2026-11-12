# ADR-0003: Ports and adapters with a single composition root

- Status: accepted
- Date: 2026-11-12

## Context

The model provider, the platform (simulated today, live later), storage and
telemetry will all change independently. Use cases must be testable with fakes
and must not import FastAPI, SQL drivers or exporters.

## Options considered

1. A DI framework (dependency-injector, punq).
2. FastAPI `Depends` all the way down.
3. `typing.Protocol` ports, constructor injection, and one hand-written
   composition root (the "bootstrap" approach from *Architecture Patterns with
   Python*).

## Decision

Option 3. Ports live in [`domain/ports.py`](../../app/domain/ports.py) and
[`application/ports.py`](../../app/application/ports.py). Only
[`core/container.py`](../../app/core/container.py) names concrete classes.
Layers are `domain`, `application`, `infrastructure`, `presentation`, `core`.
[`tests/test_architecture.py`](../../tests/test_architecture.py) enforces the
dependency rule, port conformance and size budgets.

## Consequences

- Positive: explicit wiring that reads top to bottom; tests, evals and the HTTP
  app build the service the same way; adapters are swappable.
- Negative: the composition root must be kept current by hand; no
  auto-wiring.
- Follow-up: none.
