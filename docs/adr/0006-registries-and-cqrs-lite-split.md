# ADR-0006: Registries for extension points and a CQRS-lite split

- Status: accepted
- Date: 2026-11-12

## Context

A review found if/elif chains that had to be edited for every new tool kind,
provider or event type (`act_node`, `make_llm`, `event_display`,
`render_working_memory`) and a 552-line `RunService` that mixed commands,
queries, task management and step logic.

## Options considered

1. Keep the chains; add tests.
2. Registries keyed by name, plus splitting the service by responsibility.

## Decision

Option 2.

| Extension point | Registry |
| --- | --- |
| Tool calls | `ToolCallDispatcher.register` in [`tool_dispatch.py`](../../app/application/tool_dispatch.py) |
| LLM providers | `PROVIDERS` in [`llm/factory.py`](../../app/infrastructure/llm/factory.py) |
| Operator event views | `EVENT_VIEWS` in [`views/events.py`](../../app/presentation/views/events.py) |
| Working-memory sections | `WORKING_MEMORY_SECTIONS` in [`context/builder.py`](../../app/application/context/builder.py) |

The service is split into `RunService` (commands), `RunQueries` (reads),
`GraphRunner` (tasks) and `AgentSteps` (the facade graph nodes call).

## Consequences

- Positive: adding a provider, event view or section is one entry;
  architecture tests check that every tool has a handler and every configurable
  provider has a builder. Read routes cannot mutate state.
- Negative: more, smaller files; a reader follows one more indirection.
