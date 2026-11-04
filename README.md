# Incident triage agent

Production-ready operator console for autonomous incident investigation. Paste a production alert (or start a curated scenario): the agent plans an investigation, calls tools (metrics, logs, deploys, runbooks), maintains structured working memory, and proposes a fix. **Every production mutation stops at a durable human approval gate** with a confidence score — low confidence is bounced back to the agent instead of paging a person. Operators watch the live reasoning trace over SSE, can edit / reject / redirect, and can resume after a crash from the last checkpoint.

![Empty console](docs/screenshots/01-empty.png)

![Running / thinking](docs/screenshots/02-running.png)

![Approval gate](docs/screenshots/approval-gate.png)

![Resolved](docs/screenshots/resolved.png)

![Dark mode](docs/screenshots/dark-mode.png)

![Mobile](docs/screenshots/03-mobile.png)

Screenshots under [`docs/screenshots/`](docs/screenshots/). Recapture with `python -m scripts.capture_screenshots`. Operator walkthrough: [`docs/DEMO.md`](docs/DEMO.md) and [`docs/screenshots/walkthrough.mp4`](docs/screenshots/walkthrough.mp4).

---

## Architecture

```mermaid
flowchart TD
  UI[React operator console<br/>Vite + TanStack Query + Zustand] -->|REST + SSE| API[FastAPI app/main.py]
  API --> RT[Runtime facade]
  RT --> LG[LangGraph StateGraph]
  LG --> P[prepare]
  P --> A[act: LLM + parallel reads]
  A -->|write / ask| G[approval / input<br/>interrupt + Command resume]
  A -->|continue| P
  G --> P
  A -->|finish / budget| END([END])
  LG --> CP[(LangGraph checkpointer<br/>SQLite or Postgres)]
  RT --> Store[(Store: runs · events · inbox · memory)]
  RT --> LLM[Gemini / Anthropic / OpenAI / scripted]
  RT --> Tools[Typed tool registry]
  Tools --> Sim[Simulated Kubernetes cluster]
```

### Stack

| Layer | Choice |
|---|---|
| Frontend | Vite, React 19, TypeScript, TanStack Query, Zustand, React Router (hash), Tailwind CSS v4, Radix primitives, sonner, lucide-react, react-syntax-highlighter |
| Backend | FastAPI, LangGraph, SQLAlchemy 2 + Alembic, structlog, Prometheus `/metrics`, OpenTelemetry GenAI spans |
| LLM | Gemini (default), Anthropic, OpenAI, or offline deterministic provider for CI / local development |
| Serving | FastAPI mounts `frontend/dist` at `/` in production; Vite proxies `/api` (+ SSE) in development |
| Packaging | Multi-stage Docker (Node build → Python runtime), Compose, GitHub Actions + GitLab CI |

| Path | Role |
|---|---|
| `frontend/` | Production operator UI (Vite + React + TypeScript) |
| `app/agent/graph.py` | LangGraph `StateGraph` (`prepare` → `act` → gates → loop) |
| `app/agent/nodes/` | Node implementations; HITL via `interrupt` / `Command(resume=...)` |
| `app/runtime.py` | Lifecycle facade: create / pause / cancel / approve; drives the graph |
| `app/config/` | `pydantic-settings` v2 (env-only overrides via `Settings.from_env()`) |
| `app/context/` | Layered prompt: system + working memory + compacted transcript |
| `app/tools/` | Typed schemas; read / write / meta kinds |
| `app/llm/` | Neutral history + provider adapters + Gemini 429 → fallback model |
| `app/db/` | SQLAlchemy 2 models + Alembic migrations |
| `app/store.py` | Sync Store facade (UI/SSE source of truth) with checkpoint CAS |
| `app/observability/` | structlog, OTel GenAI spans, Prometheus `/metrics`, optional Langfuse |
| `app/main.py` | HTTP API, auth, CORS, CSP, health/metrics, SSE, SPA |
| `scripts/quickstart.sh` | One-command local boot (Python + frontend build + uvicorn) |

Lifecycle:

```
queued → running ⇄ awaiting_approval / awaiting_input / paused / needs_attention → completed | failed | cancelled
                 ↘ interrupted (crash / mid-approval) → resume (idempotent)
```

---

## Prerequisites

- Python **3.11+** (3.12 recommended; CI uses 3.12)
- Node.js **20+** (22 recommended) with npm — required to build the React UI
- `make` optional
- Docker optional (for Compose)
- A Gemini API key **only if** you want a live model (the offline deterministic provider works without one)

---

## Installation

```bash
git clone https://github.com/Zulfiqar7862/incident-triage-agent.git
cd incident-triage-agent
make install          # .venv + requirements-dev.txt + frontend npm ci + pre-commit
# or:
python3 -m venv .venv && .venv/bin/pip install -r requirements-dev.txt
cd frontend && npm ci && cd ..
```

Copy env defaults if you need a live model:

```bash
cp .env.example .env   # set GEMINI_API_KEY (never commit .env)
```

---

## Configuration

See [`.env.example`](.env.example). Important variables:

| Variable | Default | Notes |
|---|---|---|
| `LLM_PROVIDER` | `auto` | `auto` \| `gemini` \| `anthropic` \| `openai` \| `scripted` |
| `GEMINI_API_KEY` | — | Live Gemini; omit to use the offline deterministic provider |
| `REQUIRE_LLM` | `true` | Set `false` to allow scripted fallback without a key |
| `API_TOKEN` | — | Bearer token required outside localhost |
| `CORS_ORIGINS` | empty | Comma-separated; empty = same-origin |
| `DB_PATH` | `data/agent.db` | SQLite path (or set `DATABASE_URL` for Postgres) |
| `SCRIPTED_DELAY_S` | `0.8` | Offline provider pacing for local / CI |

Secrets are env-only, redacted in logs, and never committed.

---

## Running locally

### One command (production build of the UI)

```bash
make quickstart
# → http://127.0.0.1:8000
```

Builds the React app into `frontend/dist` (when `npm` is available) and serves it from FastAPI.

### Dev with hot reload

Terminal 1 — API:

```bash
make dev
```

Terminal 2 — Vite (proxies `/api`, health, metrics, and SSE to `:8000`):

```bash
make frontend-dev
# → http://127.0.0.1:5173
```

### Production-style (prebuilt UI)

```bash
make frontend   # npm run build
make run        # uvicorn serves frontend/dist at /
```

---

## Deployment

```bash
docker compose up --build
# multi-stage image: Node builds frontend/, Python runtime serves it
```

Health: `GET /healthz`, readiness: `GET /readyz`, metrics: `GET /metrics`. One uvicorn worker: a run is owned by the process that drives it (see Design decisions).

---

## CI pipeline

GitHub Actions (`.github/workflows/ci.yml`) and GitLab CI (`.gitlab-ci.yml`):

1. **test** — ruff, mypy, pytest, scripted evals; Playwright UI E2E (offline scenario + no console errors)
2. **frontend** — `npm ci`, lint (oxlint), `tsc --noEmit`, Vitest, production build
3. **docker** — multi-stage image build (needs test + frontend)

---

## Testing

```bash
make test                 # backend unit / API
make lint && make typecheck
make eval                 # scripted offline evals
make frontend-test        # lint + typecheck + Vitest
python -m scripts.e2e_ui  # Playwright full offline scenario incl. approval
python -m scripts.run_e2e_live   # live Gemini (needs GEMINI_API_KEY)
```

Results for live Gemini runs are recorded in [`docs/E2E_RESULTS.md`](docs/E2E_RESULTS.md). Hardening notes: [`docs/HARDENING.md`](docs/HARDENING.md).

---

## Project structure

```
app/                 FastAPI + LangGraph agent
frontend/            Vite React TypeScript operator console
  src/components/    layout, runs sidebar, timeline, approval, tools
  src/hooks/         SSE stream with reconnect + reducer
  src/store/         Zustand UI state (theme, thinking phase)
scenarios/           Curated incident scenarios
runbooks/            Tool-backed runbook content
evals/               Offline deterministic evaluation harness
scripts/             quickstart, screenshots, UI E2E, live E2E
docs/                HARDENING, E2E_RESULTS, DEMO walkthrough, screenshots
```

---

## Requirement mapping

| Take-home / ops need | Where it lands |
|---|---|
| Autonomous planning + tool use | LangGraph `prepare`/`act`, typed tool registry |
| Error recovery / budgets | Retries, identical-call caps, token/cost budgets |
| Human-in-the-loop | Durable approval interrupt + audit (`X-Operator`) |
| Resumable state | LangGraph checkpointer + Store CAS |
| Live operator UX | React console, SSE timeline, approval card, pause/resume/cancel |
| Observability | structlog, Prometheus, OTel GenAI, optional Langfuse |
| Reproducible CI | Scripted offline provider, evals, frontend Vitest, Playwright UI |

---

## Design decisions

| Decision | Why | Trade-off |
|---|---|---|
| React + Vite for the console | Production operator UX, typed contracts, testable components | Requires Node to build; FastAPI serves the built assets |
| TanStack Query + Zustand | Server state vs ephemeral UI state without Redux ceremony | Two state layers to learn |
| Hash routing | Deep-link runs without server rewrite rules | Hash URLs instead of path URLs |
| Sync Store facade | Simple SSE/UI path | Sync work on the event loop at small scale |
| One uvicorn worker | Run ownership / in-process concurrency | Horizontal scale needs a shared lease story |
| Scripted offline provider | Deterministic CI and local development without keys | Not a substitute for live model evals |
| Multi-stage Docker | Single image ships UI + API | Image build needs Node stage |

---

## Known limitations

- Dual persistence (Store + LangGraph checkpointer) must stay aligned; CAS conflicts surface as HTTP 409.
- In-process concurrency cap — not distributed leases.
- Shared bearer token + self-declared `X-Operator` (fine for a console; not multi-tenant IAM).
- Event log / checkpoint growth — budgets bound local runs; production needs retention.
- Simulated cluster tools — not a live Kubernetes control plane.

See also [`docs/HARDENING.md`](docs/HARDENING.md).

---

## Roadmap

- Path-based SPA routing behind the reverse proxy
- Shared run leases for multi-worker / multi-replica
- Event retention / archival policy
- Stronger operator identity (OIDC) instead of self-declared names
- Live cluster adapters behind the same tool schemas

---

## License

See repository for terms. Built as a Senior Software Engineer – AI take-home for Intuitive Technology Partners.
