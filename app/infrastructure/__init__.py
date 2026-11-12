"""Infrastructure adapters behind the ``app.domain.ports`` Protocols.

store.py         RunStorePort: SQLite runs / hash-chained events / inbox / memories
mock_cluster.py  ClusterPort: simulated platform (scenarios + runbooks)
runbooks.py      local runbook search used by the cluster adapter
checkpointer.py  LangGraph checkpointer (SQLite or Postgres)
cluster.py       cluster adapter factory
llm_factory.py   LLM Strategy factory (providers live in app.llm)
"""
