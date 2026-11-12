# AI assistance transcript

> Historical record. File paths here predate the layered restructure of 2026-11-12; see the [LLD](LLD.md#1-project-structure) for the current layout.

**Disclosure:** this file is a curated implementation summary, not a complete or
verbatim AI conversation transcript. It does not prove that every change received
human review. Full conversation history is not included in this source release;
no missing interactions have been reconstructed or invented.

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

## Local release follow-up
AI-assisted local work also extracted domain/application/infrastructure boundaries,
added run feature hooks, and rebuilt operator presentation around structured tool
observations rather than raw model/log text. Project-local skills and test results
are recorded in `docs/LOCAL_RELEASE.md` and `.claude/skills/PROVENANCE.md`.
The follow-up was first prepared as an uncommitted source snapshot against
baseline `2096a05`. Publication to the existing repository was subsequently
authorized explicitly; Git history records the published changes. This summary
is not a reconstructed conversation log.
