# Architecture Decision Records

Short records of decisions that shape the system. Format: MADR-style
(context, options, decision, consequences), using the
[`architecture-decision-records`](../../.claude/skills/architecture-decision-records/SKILL.md)
skill. Copy [`template.md`](template.md) for a new record and never edit an
accepted record's decision; supersede it with a new one.

| ADR | Title | Status |
| --- | --- | --- |
| [0001](0001-langgraph-interrupt-for-human-gates.md) | LangGraph `interrupt()` for human gates | Accepted |
| [0002](0002-sqlite-store-with-hash-chained-event-log.md) | SQLite Store with CAS checkpoints and a hash-chained event log | Accepted |
| [0003](0003-ports-and-adapters-with-composition-root.md) | Ports and adapters with a single composition root | Accepted |
| [0004](0004-deterministic-scripted-llm-provider.md) | Deterministic scripted LLM provider for CI and offline use | Accepted |
| [0005](0005-single-worker-process-model.md) | Single worker process model | Accepted |
| [0006](0006-registries-and-cqrs-lite-split.md) | Registries for extension points and a CQRS-lite split | Accepted |
