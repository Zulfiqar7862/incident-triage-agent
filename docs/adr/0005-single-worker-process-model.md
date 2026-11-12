# ADR-0005: Single worker process model

- Status: accepted
- Date: 2026-11-12

## Context

A run is a long-lived asyncio task with in-memory pause/cancel flags and a
per-run gate lock. Running several workers would need distributed ownership of
runs.

## Options considered

1. Several uvicorn workers with run leases in the database.
2. One process with one worker; `MAX_CONCURRENT_RUNS` caps load.

## Decision

Option 2. `GraphRunner` owns the tasks; `RunControls` and `GateLocks` hold
in-memory state. The Dockerfile starts uvicorn with `--workers 1`.

## Consequences

- Positive: simple, correct run ownership; no lease expiry edge cases.
- Negative: no horizontal scale; a process crash interrupts every active run
  (they are marked `interrupted` and can be resumed).
- Follow-up: leases plus database-backed control flags, as described in
  [HLD §13](../HLD.md#13-scalability-and-evolution).
