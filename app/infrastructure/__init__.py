"""Infrastructure adapters behind the domain and application ports.

persistence/    RunStorePort: SQLite Store (runs, hash-chained events, inbox, memories),
                LangGraph checkpointer, SQLAlchemy models + Alembic migrations
cluster/        ClusterPort: simulated platform (scenarios + runbooks) and its factory
llm/            LLMPort Strategies (Gemini, Anthropic, OpenAI, scripted) and the provider registry
observability/  TelemetryPort adapter, structlog, OpenTelemetry, Prometheus, Langfuse
"""
