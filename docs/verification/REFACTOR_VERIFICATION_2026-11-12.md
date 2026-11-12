# Verification after the layered refactor (2026-11-12)

Commit under test: `551c146` (pushed to `main`). Times are CET (UTC+1).

## CI

GitHub Actions run 43201293459 (started 11:32 CET): `test`, `frontend` and
`docker` jobs all passed.
https://github.com/Zulfiqar7862/incident-triage-agent/actions/runs/43201293459

## Fresh clone, following the README literally

Clean `git clone` into an empty directory, no `.env`, no API key in the
environment (so `LLM_PROVIDER=auto` selected the scripted provider).

| Step (README command) | Result |
| --- | --- |
| `make install` | OK |
| `make test` | 94 passed, 1 skipped (live test) |
| `make lint` (ruff check + format check) | OK, 103 files formatted |
| `make typecheck` (mypy) | No issues in 86 source files |
| `make eval` | 3/3 scenarios passed (7, 7, 9 steps; 21,800 / 22,329 / 40,489 tokens) |
| `make frontend-test` | oxlint, tsc and Vitest: 37 tests passed |
| `python -m playwright install chromium`, `npm run build`, `python -m scripts.e2e_ui` | `e2e ui OK`, no console errors |
| `make quickstart` → `http://127.0.0.1:8000` | Ready, provider `scripted` |
| HTTP API audit (23 checks: probes, runs, SSE resume, approve, reject, message, pause/resume, cancel, 409/404/422, emergency stop, hash-chain verify, metrics) | 23/23 passed |
| Playwright operator walkthrough (3 scenarios, edit-and-approve, reject, pause/resume/stop, dark mode, mobile) | All runs reached the expected status; no console errors or warnings; no raw identifiers or stack traces in the operator view |

## Not covered here

- Live-model runs were not repeated after the refactor; the latest live
  Gemini results are in [E2E_RESULTS.md](../E2E_RESULTS.md) and predate it.
  The provider adapters were split into modules without logic changes, and
  `tests/test_gemini.py` covers the Gemini adapter against a mocked API.
- Docker was not available on the verification machine; the CI `docker` job
  built the image.
