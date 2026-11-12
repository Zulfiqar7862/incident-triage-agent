# PyCharm-style verification from a fresh clone — 2026-11-12

Commit under test: `cb67f6f01ef29bca6ad4b40fb30bed002e742470`
("docs: add high-level and low-level design, architecture review guide, and PyCharm run configurations").
Run on 2026-11-12, 07:14–07:16 CET, Linux, Python 3.13.5, Node 24.22.1, npm 11.21.1,
Playwright 1.64.1 (Chromium). The clone had no `.env` and no API key.

The steps follow [PYCHARM_DEMO.md](../PYCHARM_DEMO.md). PyCharm itself was not
launched (headless machine); the commands were generated from the `.run/*.run.xml`
files so they match what the IDE runs.

## 1. Setup (sections 2–3 of the guide)

```text
git clone <repo> verify-pycharm-20261112-071422
python3 -m venv .venv && .venv/bin/pip install -r requirements-dev.txt   -> OK (Python 3.13.5)
cd frontend && npm ci && npm run build                                   -> added 302 packages; built; dist/index.html present
```

## 2. Run configuration XML

All five files parse with `xml.etree.ElementTree`; the compound **Full app**
references only configurations that exist.

| File | Type | Command / target | Env |
| --- | --- | --- | --- |
| `Backend (uvicorn).run.xml` | Python, module mode | `uvicorn app.main:app --host 127.0.0.1 --port 8000`, cwd `$PROJECT_DIR$` | `PYTHONUNBUFFERED=1`, `LLM_PROVIDER=scripted`, `REQUIRE_LLM=false` |
| `Tests (pytest).run.xml` | pytest | `$PROJECT_DIR$/tests`, `-q --ignore=tests/test_e2e_live.py` | same + `TOOL_BACKOFF_S=0.01` |
| `Architecture tests.run.xml` | pytest | `$PROJECT_DIR$/tests/test_architecture.py`, `-q` | same + `TOOL_BACKOFF_S=0.01` |
| `Frontend dev (npm).run.xml` | npm | `run dev` in `frontend/package.json` | — |
| `Full app.run.xml` | compound | Backend (uvicorn) + Frontend dev (npm) | — |

No keys, tokens, or secrets appear in any `.run` file.

## 3. Backend (uvicorn), started exactly as the configuration defines

```text
cd . && env PYTHONUNBUFFERED=1 LLM_PROVIDER=scripted REQUIRE_LLM=false .venv/bin/python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
GET /healthz       -> {"ok":true}
GET /readyz        -> {"ok":true,"llm":"scripted"}
GET /              -> <title>Incident triage agent</title>  (built UI served)
GET /api/scenarios -> ['cache-oom-injection', 'db-pool-regression', 'upstream-oom']
```

Playwright against that server (operator "Demo Reviewer", scenario
"Checkout errors after a deploy", **Start triage** → **Approve fix**):

```text
status=completed steps=7 events=56 approval_gate_s=6.4 total_s=8.3
approval.decided: ['approved']
verify: {'ok': True, 'events': 56}        (GET /api/runs/{run_id}/events/verify)
console_errors: []
```

The approval screen matched `docs/screenshots/approval-gate.png` (same layout and
content), so the screenshots were not refreshed.

## 4. Tests, run as the configurations define

```text
Tests (pytest):      env ... .venv/bin/python -m pytest tests -q --ignore=tests/test_e2e_live.py -> 69 passed, 1 warning
Architecture tests:  env ... .venv/bin/python -m pytest tests/test_architecture.py -q           -> 10 passed
```

The one warning is SQLite connection teardown noise from the crash/restart
tests (a `ResourceWarning` raised inside LangGraph); it does not affect results.

## 5. Other checks in the same clone

```text
ruff check app tests evals scripts                       -> All checks passed!
mypy -p app                                              -> no issues found in 68 source files
python -m evals.run_evals --provider scripted            -> Passed 3/3
npm run lint (oxlint --deny-warnings)                    -> exit 0
npm run typecheck (tsc -b)                               -> OK
npx vitest run                                           -> 11 files, 32 tests passed
python -m scripts.e2e_ui (Playwright, own server :8878)  -> e2e ui OK, console warnings [], errors [], 8.9 s
git status (clone)                                       -> clean
```

## 6. Documentation checks

- 13 mermaid diagrams (README, HLD, LLD) rendered with `@mermaid-js/mermaid-cli`
  12.2.0 (mermaid 12.3.0): all pass.
- Every relative link and `#L` anchor in README, HLD, LLD, ARCHITECTURE_REVIEW and
  PYCHARM_DEMO resolves to an existing file and line.
- Backticked endpoints, classes, functions, and settings in those files were
  matched against the code by script. Every non-match was reviewed by hand: they
  are pre-refactor paths in the "before" column of the review guide, bare file
  names, upper-case environment names of `Settings` fields, and the clone URL.

## Not covered

- PyCharm's GUI was not driven; the run configurations were validated as XML and
  their exact commands executed. Import into a real IDE is expected to work but
  was not observed here.
- **Frontend dev (npm)** was not started (the built UI was used); it needs an
  edition with JavaScript support.
- No live-model run was part of this check.
