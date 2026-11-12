# ADR-0002: SQLite Store with CAS checkpoints and a hash-chained event log

- Status: accepted
- Date: 2026-11-12

## Context

The UI needs a live, replayable activity stream; reviewers need an audit trail
whose tampering is detectable; concurrent requests (double clicks, two
operators) must not overwrite each other's changes. The service must run on a
laptop with no external database.

## Options considered

1. Postgres from day one.
2. LangGraph checkpoints as the only state.
3. A small SQLite Store: a `runs` row with a `checkpoint_version`
   compare-and-set, an append-only `events` table with a per-run SHA-256 chain,
   an operator inbox and a memories table.

## Decision

Option 3, behind role Protocols (`RunRepository`, `EventLog`, `OperatorInbox`,
`IncidentMemory`, `StoreHealth`) in [`ports.py`](../../app/domain/ports.py).
Implementation: [`store.py`](../../app/infrastructure/persistence/store.py).
SQLAlchemy models and an Alembic migration mirror the tables for a later move.

## Consequences

- Positive: zero setup; SSE is a simple tail of `events` by `seq`; lost updates
  become HTTP 409; `/events/verify` detects edited or deleted events.
- Negative: the chain is tamper-evident, not tamper-proof; someone with write
  access can rewrite it all. Synchronous SQLite calls run on the event loop.
- Follow-up: signed or WORM export of the chain; Postgres Store for scale-out.
