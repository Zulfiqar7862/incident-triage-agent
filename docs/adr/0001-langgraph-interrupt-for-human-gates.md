# ADR-0001: LangGraph `interrupt()` for human gates

- Status: accepted
- Date: 2026-11-12

## Context

The agent must stop before every production change and wait, possibly for
hours and across a process restart, for an operator to approve, edit or reject
it. It must then resume exactly where it stopped, without repeating the change.

## Options considered

1. Hand-written loop with a `pending` field and custom resume logic.
2. A workflow engine or task queue (Temporal, Celery).
3. LangGraph `StateGraph` with `interrupt()` and `Command(resume=...)`, plus a
   checkpointer keyed by run id.

## Decision

Option 3. The graph has `prepare`, `act`, `approval` and `input` nodes. Gate
nodes call `interrupt(pending)`; `GraphRunner` resumes with
`Command(resume=decision)`. See [`gates.py`](../../app/application/agent/nodes/gates.py)
and [`graph_runner.py`](../../app/application/graph_runner.py).

## Consequences

- Positive: durable pause and resume without custom state machinery; the
  graph topology is explicit and testable (`tests/test_langgraph.py`).
- Negative: two checkpoints exist (Store row and LangGraph checkpoint) and must
  stay aligned. Gate nodes re-read the Store after `interrupt()` returns.
- Negative: an extra framework dependency, compared with option 1.
- Follow-up: when both stores move to Postgres, write them in one transaction.
