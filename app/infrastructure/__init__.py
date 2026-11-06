"""Infrastructure adapters: persistence, cluster sim, LLM providers, checkpointer.

Concrete implementations live in existing modules (`app.store`, `app.mock_env`,
`app.llm`, `app.agent.checkpointer`) and satisfy `app.domain.ports` Protocols.
This package documents the boundary; prefer importing the concrete modules
directly to avoid a noisy rename of the whole tree.
"""
