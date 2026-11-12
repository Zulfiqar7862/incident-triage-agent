# PyCharm Setup and Interview Demo

How to open, run, test, and demo the project from PyCharm. The shared run
configurations live in [`.run/`](../.run) and appear in the run/debug selector
automatically when the project is opened.

Related: [README](../README.md) · [HLD](HLD.md) · [LLD](LLD.md) ·
[Architecture review guide](ARCHITECTURE_REVIEW.md)

## 1. Prerequisites

| Tool | Version | Check |
| --- | --- | --- |
| Python | 3.12 or 3.13 | `python3 --version` |
| Node.js + npm | Node 22.12+ or 24 LTS | `node --version` |
| PyCharm | 2024.3 or newer | The **Frontend dev (npm)** configuration needs JavaScript support (PyCharm Professional / paid tier). Without it, use the built UI served by the backend (section 4). |
| Git | any | `git --version` |

No API key is needed. All run configurations use the offline scripted model.

## 2. Open the project and set the interpreter

1. **File → Open…** and choose the cloned `incident-triage-agent` folder (or
   **Get from VCS** with `https://github.com/Zulfiqar7862/incident-triage-agent.git`).
2. Create the virtual environment from PyCharm's terminal (**View → Tool Windows → Terminal**):

   ```bash
   python3 -m venv .venv
   .venv/bin/pip install -r requirements-dev.txt        # Windows: .venv\Scripts\pip
   ```

3. **Settings → Project → Python Interpreter → Add Interpreter → Add Local
   Interpreter → Existing**, and select `.venv/bin/python`
   (Windows: `.venv\Scripts\python.exe`). The run configurations use the project
   interpreter, so nothing else needs setting.

## 3. Build the frontend once

```bash
cd frontend
npm ci
npm run build          # writes frontend/dist, which the backend serves at /
cd ..
```

## 4. Run configurations

| Configuration | What it runs | Use it for |
| --- | --- | --- |
| **Backend (uvicorn)** | `python -m uvicorn app.main:app --host 127.0.0.1 --port 8000` in `$PROJECT_DIR$` with `LLM_PROVIDER=scripted`, `REQUIRE_LLM=false` | The full app at <http://127.0.0.1:8000> (API + built UI) |
| **Tests (pytest)** | `pytest tests -q --ignore=tests/test_e2e_live.py` with the scripted model | The whole offline backend suite, in the PyCharm test runner |
| **Architecture tests** | `pytest tests/test_architecture.py -q` | Layer boundaries and port conformance |
| **Frontend dev (npm)** | `npm run dev` in `frontend/` | Hot-reload UI at <http://127.0.0.1:5173> (proxies `/api` to `:8000`) |
| **Full app** (compound) | Backend + Frontend dev together | Development with hot reload |

For a demo, **Backend (uvicorn)** alone is enough once `frontend/dist` exists.

Configuration notes:

- Environment variables set in a configuration override `.env`. The backend
  loads `.env` with `setdefault`, so `LLM_PROVIDER=scripted` wins even if `.env`
  selects Gemini.
- To demo a live model, duplicate **Backend (uvicorn)**, remove the
  `LLM_PROVIDER` / `REQUIRE_LLM` entries, and keep `GEMINI_API_KEY` in your local
  `.env` (never in the run configuration or in git).
- **Tests (pytest)** skips `tests/test_e2e_live.py` on purpose: that file loads
  `.env` and would call a real model if a key is present.

## 5. Interview demo script (5–7 minutes)

| Time | Click / show | Say |
| --- | --- | --- |
| 0:00 | README in PyCharm's Markdown preview; the links at the top | "This is a governed incident-triage agent: it investigates alerts with tools, stops for human approval before any change, and survives restarts. The platform it operates on is simulated." |
| 0:45 | [HLD](HLD.md) section 2–3 diagrams | "FastAPI and a React console in front, a LangGraph state machine inside, SQLite for the run store and checkpoints, a pluggable LLM." |
| 1:30 | Run **Backend (uvicorn)**; open <http://127.0.0.1:8000> | "Offline scripted model, so the demo is deterministic." |
| 2:00 | Enter a name, pick **Checkout errors after a deploy**, click **Start triage** | "Progress streams over Server-Sent Events. Each tool call is shown as a plain sentence, not raw JSON." |
| 2:45 | Approval card: click **Edit before approving**, change the reason, click **Approve fix** | "Writes never run without approval. Low-confidence or unknown-service proposals are blocked before they reach me." |
| 3:30 | Final report; then start a second run and use **Pause** / **Resume** / **Stop** | "Pause takes effect at the next step boundary; Stop cancels the in-flight task." |
| 4:00 | PyCharm terminal: `curl -s http://127.0.0.1:8000/api/runs \| head -c 400` then `curl -s http://127.0.0.1:8000/api/runs/<run_id>/events/verify` | "Every event is SHA-256 hash-chained per run; this endpoint re-computes the chain." |
| 4:30 | [LLD](LLD.md) sections 2, 4, 5 (layers, graph, lifecycle) | "Domain is pure Python, application depends on ports, adapters are injected at the composition root." |
| 5:00 | [ARCHITECTURE_REVIEW.md](ARCHITECTURE_REVIEW.md) sections 2–3; Ctrl/Cmd-click a link such as `app/application/run_service.py#L59` | "Each pattern and SOLID principle points to real code and a test." |
| 5:45 | Run **Architecture tests**, then **Tests (pytest)** | "The import rules are tests, so a forbidden dependency fails CI." |
| 6:30 | `tests/test_architecture.py` and `.github/workflows/ci.yml` | "CI runs lint, types, architecture, unit, evals, the frontend suite, a browser E2E, and a Docker build." |

## 6. Troubleshooting

| Symptom | Fix |
| --- | --- |
| `Address already in use` on port 8000 | Stop the other process (`lsof -i :8000` on macOS/Linux, `netstat -ano \| findstr :8000` on Windows) or change `--port` in the configuration. If you change it, also change the proxy target in `frontend/vite.config.ts` for the dev server. |
| Port 5173 busy | Vite picks the next free port and prints it; use that URL. |
| Page says "Frontend not built" | Run `npm ci && npm run build` in `frontend/` (section 3), then refresh. |
| `npm ci` fails or Vite refuses to start | Check `node --version`; use Node 22.12+ or 24 LTS. |
| **Frontend dev (npm)** shows as unknown or broken | Your PyCharm edition lacks JavaScript support. Run `npm run dev` in the terminal, or use **Backend (uvicorn)** with the built UI. |
| `ModuleNotFoundError: app` or `uvicorn` | The configuration is not using `.venv`. Re-select the interpreter (section 2) and confirm the working directory is the project root. |
| Startup fails with a `ConfigError` about a missing API key | The configuration lost `LLM_PROVIDER=scripted` and `.env` asks for a live model; add the variable back, or set the key in `.env`. |
| API returns 401 | `API_TOKEN` is set in your `.env`. Remove it for local demos, or send `Authorization: Bearer <token>`. |
