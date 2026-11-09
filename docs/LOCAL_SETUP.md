# Run the supplied source locally

For the published repository, clone and enter the checkout:

```bash
git clone https://github.com/Zulfiqar7862/incident-triage-agent.git
cd incident-triage-agent
```

If you received a source ZIP instead, extract it and open its `incident-agent`
directory. The archive has no `.git` directory; the install/run steps below work
for either distribution.
Use Bash on Linux/macOS (or WSL on Windows). Python 3.12/3.13 and Node 22.12+ or
24 LTS are the intended versions; this release was exercised on Linux with Python
3.13.5, Node 24.22.1, and npm 11.21.1. CI configuration targets Python 3.12 / Node 22.

## Install and run without credentials

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements-dev.txt
(cd frontend && npm ci && npm run build)
LLM_PROVIDER=scripted REQUIRE_LLM=false .venv/bin/python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

Open http://127.0.0.1:8000. Enter an operator name, choose an incident, and select
**Start triage**. Read the observed checks, review the proposed action/evidence and
risk, then approve/edit or reject it. Pause/resume and Stop remain available.
The server creates local SQLite state in `data/`; restart it with the same data
paths to retain runs. No database or previous run is bundled in the archive.

Alternatively `LLM_PROVIDER=scripted REQUIRE_LLM=false bash scripts/quickstart.sh`
installs dependencies, builds, and starts the app. First installation requires
network access or cached packages. No `make`, Git repository, hooks, API key, or
cloud/cluster credentials are needed. Do not use `make install` for the ZIP: its
Git-hook step is only for a Git checkout.

For frontend hot reload, leave the API running and use a second terminal:
`cd frontend && npm run dev -- --host 127.0.0.1`. Open http://127.0.0.1:5173;
Vite proxies API and SSE to port 8000. Use 8000 for the built single-server app.

## Optional live model

Copy `.env.example` to `.env` only if you need custom settings. Secret fields in
the example are blank. Set a provider/key privately and `REQUIRE_LLM=true` if you
want startup to fail without a live provider. Never share `.env`. Model selection,
network availability, provider limits, and paid token usage are your responsibility.
All platform tools still target the **simulated cluster**, even with a live model;
this release does not access real Kubernetes or cloud resources.
Bind locally as above; set your own `API_TOKEN` and appropriate access controls
before exposing the API elsewhere. Operator identity is self-declared, not IAM.

## Verify

```bash
.venv/bin/ruff check app tests evals scripts
.venv/bin/ruff format --check app tests evals scripts
.venv/bin/mypy -p app
TOOL_BACKOFF_S=0.01 .venv/bin/pytest -q -m 'not live'
TOOL_BACKOFF_S=0.01 .venv/bin/python -m evals.run_evals --provider scripted
(cd frontend && npm run lint && npm run typecheck && npm test && npm run build)
.venv/bin/python -m playwright install chromium
TOOL_BACKOFF_S=0.01 SCRIPTED_DELAY_S=0.12 .venv/bin/python -m scripts.e2e_ui
.venv/bin/python -m scripts.capture_screenshots
```

Linux hosts may also need Playwright system libraries:
`.venv/bin/python -m playwright install --with-deps chromium` (may require sudo).
The automated browser suites use temporary databases and local ports 8878/8877;
stop any process occupying those ports first. Rebuild the frontend before E2E
when changing its source. Capture output is under `docs/screenshots/`.

`cd frontend && npm run format:check` is a separate known formatting gate: untouched
baseline files still fail it. See `LOCAL_RELEASE.md` for exact verification scope
and remaining warnings. Live-model tests and Docker were not part of this local
release validation. The AI assistance document is a summary, not a full transcript.

## Project-local Claude skills

`.claude/skills/frontend-design` and `.claude/skills/webapp-testing` contain pinned
Apache-2.0 guidance, licenses and reviewed scripts. Claude Code can discover them
when opened in this project. See `.claude/skills/PROVENANCE.md`; these do not change
app runtime behavior or require a plugin installation. UI/UX Pro Max was consulted
separately rather than silently installing an entire unrelated toolchain.
