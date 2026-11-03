# Production hardening notes

Addressed in recent commits:

- Pydantic validation on mutating endpoints; `MAX_REQUEST_BYTES` → 413
- Env-only config via `Settings.from_env()`; secrets never logged (structlog redaction)
- Gemini `GeminiWithFallback` on 429/quota
- CORS (`CORS_ORIGINS`), CSP and related security headers
- Optimistic checkpoint CAS (`CheckpointConflict` → 409)
- mypy clean and enforced in GitHub Actions / GitLab CI

Still acknowledged (see README limitations):

- Dual persistence (Store + LangGraph checkpointer)
- Sync Store facade on the event loop
- In-memory / in-process concurrency cap (not distributed leases)
- Shared bearer token + self-declared `X-Operator`
- Unbounded event-log growth without retention policy
