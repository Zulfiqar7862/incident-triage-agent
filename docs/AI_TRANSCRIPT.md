# AI interaction log

This project was built with an AI assistant (Claude), as the assignment requires.

Put the complete, unedited transcript of that conversation here, from planning
through implementation and review. Export it from the chat interface and paste
it below, or link to a shared copy.

The git history shows how the solution evolved, including the bugs the build
surfaced and their fixes:

- the log generator cycled through a single template (`(i * 7) % 7 == 0`)
- task-launching endpoints ran in FastAPI's threadpool, where there is no event loop
- visual review in headless Chromium found mobile layout, dark-mode contrast and
  stale run-list status issues
- mutation-checking the Gemini tests showed the mock accepted responses that
  dropped Gemini's call ids; the mock was tightened until both breakages failed

---

<!-- paste original build transcript below -->

---

## Hardening session (AI-assisted, post-build)

**Asked:** take the existing take-home repo and make it production-ready / top-1%
candidate for the ITP Senior AI Engineer brief. Verify live against Gemini with
the provided API key (key kept only in local `.env`, never committed). Do not
push to GitHub.

**What changed (focused commits on top of the original 17):**

- Honor provider `Retry-After` / Gemini `retryDelay` on LLM retries; lengthen
  backoff on quota errors; cap with `LLM_MAX_BACKOFF_S`.
- Loop guard for identical repeated tool calls; `security.injection_flagged`
  when tool output contains instruction-like text; `budget.alert` events as
  step/token/cost usage crosses a configurable ratio; optional cost budget that
  pauses at `needs_attention`.
- Keyword runbook retrieval (`search_runbooks`) with three short runbooks
  (pool exhaustion, OOM crash-loop, injection-in-logs).
- OpenTelemetry GenAI-style `gen_ai.span` events on every model call; optional
  OTLP/HTTP export when `OTLP_ENDPOINT` is set (off by default).
- Third golden scenario `cache-oom-injection` (unbounded cache OOM + injection
  targeting billing). Evals gained `injection_safe` / `must_not_touch` scoring
  and optional `--judge` LLM-as-judge rubrics.
- Accept rollback *or* restart as valid fixes for the cache-oom scenario after
  live Gemini preferred rollback.
- Offline evals can force `--provider scripted` even when `REQUIRE_LLM=true`.

**Verified live (Europe/Berlin wall clock during the session):**

- `make check-llm` / `scripts.check_llm`: PASS on `gemini-3.5-flash` and on
  `gemini-3.5-flash-lite` (thought-signature replay included).
- Happy paths: `db-pool-regression` on `gemini-3.5-flash` (resolved, injection
  flagged, not followed, runbooks used); `upstream-oom` and
  `cache-oom-injection` on `gemini-3.5-flash-lite` (resolved; injection not
  followed).
- Reject-with-feedback, pause/resume, cancel: PASS.
- Kill server mid-run (`SIGKILL`) → restart → resume from checkpoint → approve
  → resolved: PASS.
- `python -m evals.run_evals --judge` on `gemini-3.5-flash-lite`: **3/3**
  passed; judge scores 2/2/2/2 on every scenario.
- Offline scripted evals: **3/3**. Unit/integration tests: **36 passed**.
- UI screenshots refreshed from a live Gemini run (approval gate, dark mode via
  `prefers-color-scheme`, resolved report).
- Docker: not available in this environment (no `docker` binary); image/Compose
  files left unchanged.
- Secret scan: Gemini key string absent from tracked files and from `git log -p`
  / `git grep` over history.

**Note for the candidate:** paste your original Claude build transcript where
the placeholder above indicates. This section only documents the later
hardening/verification pass.
