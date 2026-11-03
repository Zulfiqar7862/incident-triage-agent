# AI assistance transcript

This take-home was implemented with AI pair-programming (Cursor / Grok Bot). Human direction covered architecture choices, HITL semantics, eval design, and review of every production-facing change.

## What the AI wrote / rewrote
- LangGraph `StateGraph` migration (`app/agent/graph.py`, nodes, checkpointer factory) replacing the hand-rolled `_drive` loop while keeping the Runtime/HTTP/UI contract.
- Production stack wiring: pydantic-settings, SQLAlchemy models + Alembic initial migration, tenacity retries, structlog, OpenTelemetry SDK, optional Langfuse, prometheus-client `/metrics`.
- Package layout (`app/agent`, `app/config`, `app/tools`, `app/llm`, `app/context`, `app/memory`, `app/db`, `app/observability`).
- Tests for graph topology / interrupt-resume; README architecture + stack tradeoffs table.
- Earlier: durability fixes (mid-approval idempotency), Docker runbooks COPY, offline quickstart, golden evals.

## What stayed human-owned
- Product choices: confidence gate, dual persistence (Store + LG checkpointer), rejecting DeepEval for CI weight.
- Scenario design and scripted policy behaviour.
- Final review of secret handling (`.env` gitignored; never printed).

## DeepEval note
DeepEval was installed in a spike; it pulled a large transitive stack (including Sentry) and did not add signal beyond the existing golden harness + live Gemini evals. Kept our judge.
