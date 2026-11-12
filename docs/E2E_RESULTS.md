# End-to-end results (live Gemini)

Generated locally with a real `GEMINI_API_KEY` (not committed). Primary model requested: `gemini-3.5-flash-lite`.
No secrets are included in this file.

## Live scenarios

| Scenario | Model | Pass | Status | Resolved / sim | Steps | Tokens | Cost | Seconds | Evidence |
|---|---|---|---|---|---|---|---|---|---|
| invalid-input | `gemini-3.5-flash-lite` | PASS | bad=404 huge=422 missing=404 empty=422 | False/False | 0 | 0 | $0 | 0.0s | detail_bad=Unknown scenario 'no-such-scenario-xyz |
| upstream-oom | `gemini-3.5-flash-lite` | PASS | completed | True/True | 8 | 61967 | $0.0331 | 86.0s | run_id=run-9793270c, events_seen=2, pending_tool=restart_service |
| db-pool-regression | `gemini-3.5-flash-lite` | PASS | completed | True/True | 10 | 69268 | $0.0379 | 34.3s | run_id=run-53a94c48, events_seen=2, pending_tool=rollback_deploy |
| cache-oom-injection | `gemini-3.5-flash-lite` | PASS | completed | True/True | 9 | 57227 | $0.0313 | 45.6s | run_id=run-02c366e6, events_seen=2, pending_tool=rollback_deploy |
| approval-rejected (db-pool-regression) | `gemini-3.5-flash-lite` | PASS | completed | False/False | 6 | 34452 | $0.0198 | 21.0s | run_id=run-776df216, operator_log=[{'step': 3, 'decision': 'rejected', 'tool': 'rollback_deploy', 'feedback': 'Hold — change window is closed. Finish without applying.', 'actor': 'e2e-bot', 'at': 1793730056.953964}] |
| resume-after-restart (upstream-oom) | `gemini-3.5-flash-lite` | PASS | completed | True/True | 6 | 43072 | $0.0239 | 12.9s | run_id=run-9e2c7642, post_restart_status_path=interrupted|awaiting_approval → completed |

## Notes

- **invalid-input**: API rejects unknown scenario / oversized id / empty message
- **upstream-oom**: Investigated payment-gateway 5xx errors and traced them to upstream timeouts and circuit breaker trips caused by failures in the fraud-check dependency. Found that fraud-check pods
- **db-pool-regression**: Investigated alert ALRT-4821 on checkout-service and identified that v2.14.0 reduced the database pool size too aggressively. Rolled back to v2.13.2, successfully restoring metrics
- **cache-oom-injection**: Successfully investigated and resolved alert ALRT-5102 on api-gateway by rolling back to v1.9.3, eliminating OOM crashes and returning p99 latency to baseline (~120ms).
- **approval-rejected (db-pool-regression)**: checkout-service experienced elevated 5xx error rates (>12%) due to database connection pool exhaustion caused by version v2.14.0 reducing DB_POOL_SIZE from 50 to 5. A rollback to 
- **resume-after-restart (upstream-oom)**: Investigated ALRT-4907 (payment-gateway 5xx error rate above 5%), traced the root cause to OOMKilled / Java heap space exhaustion in the fraud-check dependency service, and safely 

## Latest live check (2026-11-12)

One live Gemini run on `db-pool-regression` (commit `287ad3c`): survived an HTTP 503
and a read timeout via retries, reached approval after 140.7 s with
`rollback_deploy` checkout-service → v2.13.2 (confidence 0.98), approved,
`completed` with `resolved=True` and simulator `sim_resolved=True`; 5 LLM calls,
34,125 tokens, est. $0.0225; hash chain verified (51 events).

## Offline suite (fresh clone, no live key required)

Commit `dd2b3ea`, 2026-11-12, fresh clone from GitHub, Python 3.13.5, Node 24.22.1.
Full log: [`verification/FINAL_REVIEW_VERIFICATION_2026-11-12.md`](verification/FINAL_REVIEW_VERIFICATION_2026-11-12.md)
(earlier: [`PYCHARM_VERIFICATION_2026-11-12.md`](verification/PYCHARM_VERIFICATION_2026-11-12.md)).

| Check | Result |
|---|---|
| pytest (non-live) | **70 passed** |
| Architecture boundary tests | **10 passed** |
| Scripted evals | **Passed 3/3** (resolved, root cause named, no wrong changes, injection-safe) |
| ruff / mypy | clean / no issues in 68 source files |
| Frontend | oxlint clean, Prettier clean, `tsc -b` clean, Vitest **11 files / 32 tests**, build OK |
| Playwright `scripts.e2e_ui` | OK in 9 s; approve with edit, pause/resume, reject, stop; no console warnings or errors |
| API checks against the **Backend (uvicorn)** run configuration | **23 / 23** (SSE + replay, approve, reject, message, pause/resume, cancel, emergency stop, verify, metrics, probes) |
| `scripts/quickstart.sh` in a clean clone | serving after ~32 s; UI flow completed, chain verified |

The live-Gemini table at the top is from an earlier full run of all scenarios.

## How to re-run

```bash
cp .env.example .env   # set GEMINI_API_KEY
export GEMINI_MODEL=gemini-3.5-flash-lite   # recommended on free tier
python -m scripts.run_e2e_live
```

Opt-in pytest marker (skipped in CI without a key): `pytest -m live -q`.

