# Final pre-review verification — 2026-11-12

Commit under test: `dd2b3eab85774a8e6bc0dfe10a6e12a5e345a740`, cloned fresh from
GitHub at 09:57 CET (log end 09:59 CET). Linux, Python 3.13.5, Node 24.22.1,
npm 11.21.1, Playwright 1.64.1 (Chromium). The clone had no `.env`.
CI for the same commit: [run 43187114416](https://github.com/Zulfiqar7862/incident-triage-agent/actions/runs/43187114416), success
(frontend, test, docker).

Steps follow the README and [PYCHARM_DEMO.md](../PYCHARM_DEMO.md); test and
backend commands are the ones defined in `.run/*.run.xml`.

## Test matrix

| Check | Command | Result |
| --- | --- | --- |
| Backend suite | `pytest tests -q -m 'not live'` | 70 passed, 1 deselected (live), 2 warnings |
| Tests (pytest) run config | `pytest tests -q --ignore=tests/test_e2e_live.py` | 70 passed, 2 warnings |
| Architecture tests run config | `pytest tests/test_architecture.py -q` | 10 passed |
| Lint / format | `ruff check`, `ruff format --check` | clean, 84 files formatted |
| Types | `mypy -p app` | no issues in 68 source files |
| Scenario evals | `python -m evals.run_evals --provider scripted` | Passed 3/3 |
| Frontend lint | `npm run lint` (oxlint, deny warnings) | exit 0 |
| Frontend format | `npm run format:check` (Prettier) | all files pass |
| Frontend types | `npm run typecheck` (`tsc -b`) | exit 0 |
| Frontend unit | `npx vitest run` | 11 files, 32 tests passed |
| Frontend build | `npm run build` | OK |
| Browser E2E | `python -m scripts.e2e_ui` | OK in 9 s; no console warnings or errors |

The warnings are SQLite connection `ResourceWarning`s raised inside LangGraph during
the crash/restart tests; they do not affect results.

## Backend started as the **Backend (uvicorn)** configuration

`env PYTHONUNBUFFERED=1 LLM_PROVIDER=scripted REQUIRE_LLM=false .venv/bin/python -m uvicorn app.main:app --host 127.0.0.1 --port 8000`

Playwright UI flow (Start triage → Approve fix): completed in 7 steps, 56 events,
approval card after 6.6 s, report after 9.0 s, hash chain `{'ok': True, 'events': 56}`,
no console errors.

API checks against the same server: **23 / 23 passed**.

| Area | Checks |
| --- | --- |
| Probes | `/healthz`, `/readyz` (`llm: scripted`), `/api/health`, `/api/scenarios` (3), `/api/tools` |
| Start + SSE | `POST /api/runs` → SSE delivered 40 events up to `approval.requested`; `Last-Event-ID` replay resumes at the next `seq` |
| Approve | `awaiting_approval` (`rollback_deploy`) → approve → `completed`, resolved; `events/verify` ok; operator name recorded on `approval.decided` |
| Reject | Rejection recorded; tool result says the change was not executed; run completes unresolved |
| Message, pause, resume | message accepted; pause → `paused`; resume → back to `awaiting_approval` |
| Cancel | cancel → `cancelled`; approve on a cancelled run → 409 |
| Emergency stop | `POST /api/emergency-stop` cancelled both active runs |
| Errors | unknown run 404; unknown scenario rejected |
| Metrics | `agent_llm_*` and `agent_tool_calls_total{tool,error}` exported |

## Quickstart path

Separate clean clone: `LLM_PROVIDER=scripted REQUIRE_LLM=false bash scripts/quickstart.sh`
was serving after about 32 s (venv, pip, `npm ci`, build). The same Playwright flow
completed (7 steps, 56 events, chain verified, no console errors).

## Live Gemini run

Run 09:50–09:53 CET on the previous commit `287ad3c` (the later commits change only
the tool-call metric, frontend formatting, and docs). Key loaded from the local
`.env` into the process environment only; it was not printed or committed.

| Item | Value |
| --- | --- |
| Provider / model reported | Gemini / `gemini-3.6-flash` (configured `gemini-3.5-flash`, fallback `gemini-3.5-flash-lite`) |
| Scenario | `db-pool-regression` |
| Recovery | one HTTP 503 ("high demand") and one read timeout, retried by `LLMGateway`; one simulated `search_logs` 504 retried by `ToolExecutor` |
| Approval | after 140.7 s: `rollback_deploy` checkout-service → v2.13.2, confidence 0.98 |
| Outcome | approved → `completed`, `resolved=True`, simulator `sim_resolved=True` |
| Usage | 5 LLM calls, 31,965 input / 2,160 output tokens, est. $0.0225, 11 tool calls, 1 tool retry |
| Audit | `events/verify` → `{'ok': True, 'events': 51}` |

## Documentation checks

- 14 mermaid diagrams (README, HLD, LLD) render with mermaid-cli 12.2.0.
- 68 `#L` anchors checked against the symbol they name; all point at the right line.
- Relative links resolve; backticked names, endpoints, and settings match the code.
- No secrets and no employer names in tracked files.
