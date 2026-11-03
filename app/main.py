"""HTTP API: agent runtime, tools, run state, a live event stream (SSE), health
and metrics endpoints, and optional bearer-token auth."""
from __future__ import annotations

import asyncio
import hmac
import json
import logging
import re
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, Optional

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse, PlainTextResponse, StreamingResponse
from pydantic import BaseModel, Field

from .config import Settings
from .context import SYSTEM_PROMPT, build_context
from .llm import make_llm
from .logging_setup import configure_logging
from .observability.tracing import configure_tracing, shutdown_tracing
from .mock_env import list_scenarios
from .runtime import InvalidInput, NotFound, Runtime, RunStateError, TooBusy
from .store import Store
from .tools import tool_schemas

STATIC = Path(__file__).resolve().parent.parent / "static"
log = logging.getLogger("api")


class CreateRun(BaseModel):
    scenario_id: str = Field(max_length=100)


class Approve(BaseModel):
    args: Optional[dict[str, Any]] = None


class Reject(BaseModel):
    feedback: str = Field("", max_length=2000)


class Message(BaseModel):
    text: str = Field(max_length=4000)


def create_app(settings: Settings | None = None, llm=None) -> FastAPI:
    settings = settings or Settings.from_env()
    configure_logging(settings.log_format, settings.log_level)
    store = Store(settings.db_path)
    runtime = Runtime(store, llm or make_llm(settings), settings)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        configure_tracing(settings.otlp_endpoint)
        n = runtime.recover()
        if n:
            log.warning("marked %d in-flight run(s) as interrupted after restart", n)
        if not settings.api_token:
            log.warning("API_TOKEN is not set: the API, including production approvals, is unauthenticated. "
                        "Set API_TOKEN before exposing this service beyond localhost.")
        log.info("ready: provider=%s model=%s", runtime.llm.provider, runtime.llm.model)
        yield
        await runtime.shutdown()
        shutdown_tracing()

    app = FastAPI(title="Incident Triage Agent", version="1.0.0", lifespan=lifespan)
    app.state.runtime = runtime

    # ---- errors and security headers -------------------------------------------------------
    @app.exception_handler(NotFound)
    async def _not_found(_: Request, exc: NotFound):
        return JSONResponse({"detail": str(exc)}, status_code=404)

    @app.exception_handler(RunStateError)
    async def _conflict(_: Request, exc: RunStateError):
        return JSONResponse({"detail": str(exc)}, status_code=409)

    @app.exception_handler(InvalidInput)
    async def _invalid(_: Request, exc: InvalidInput):
        return JSONResponse({"detail": str(exc)}, status_code=422)

    @app.exception_handler(TooBusy)
    async def _busy(_: Request, exc: TooBusy):
        return JSONResponse({"detail": str(exc)}, status_code=429, headers={"Retry-After": "30"})

    @app.middleware("http")
    async def security_headers(request: Request, call_next):
        response = await call_next(request)
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("X-Frame-Options", "DENY")
        response.headers.setdefault("Referrer-Policy", "no-referrer")
        return response

    # ---- auth ----------------------------------------------------------------------------------
    def require_auth(request: Request) -> str:
        """Returns the operator name used in the audit log."""
        if settings.api_token:
            header = request.headers.get("authorization", "")
            token = header[7:] if header.lower().startswith("bearer ") else request.query_params.get("token", "")
            if not hmac.compare_digest(token.encode(), settings.api_token.encode()):
                raise HTTPException(401, "Missing or invalid API token", headers={"WWW-Authenticate": "Bearer"})
        name = re.sub(r"[^\w .@-]", "", request.headers.get("x-operator", ""))[:64].strip()
        return name or "operator"

    # ---- UI, health, metrics (unauthenticated: no run data) ---------------------------------
    @app.get("/", include_in_schema=False)
    def index():
        return FileResponse(STATIC / "index.html")

    @app.get("/healthz")
    def healthz():
        return {"ok": True}

    @app.get("/readyz")
    def readyz():
        try:
            store.ping()
        except Exception as e:  # noqa: BLE001
            return JSONResponse({"ok": False, "db": str(e)}, status_code=503)
        return {"ok": True, "llm": runtime.llm.provider}

    @app.get("/metrics", response_class=PlainTextResponse)
    def metrics():
        lines = ["# TYPE agent_runs gauge"]
        lines += [f'agent_runs{{status="{s}"}} {n}' for s, n in store.status_counts().items()]
        lines.append("# TYPE agent_events_total counter")
        lines += [f'agent_events_total{{type="{t}"}} {n}' for t, n in store.event_counts().items()]
        lines.append("# TYPE agent_active_runs gauge")
        lines.append(f"agent_active_runs {sum(1 for t in runtime._tasks.values() if not t.done())}")
        return "\n".join(lines) + "\n"

    # ---- API ------------------------------------------------------------------------------------
    @app.get("/api/health")
    def health(_: str = Depends(require_auth)):
        return {
            "ok": True,
            "auth": bool(settings.api_token),
            "llm": {"provider": runtime.llm.provider, "model": runtime.llm.model},
            "limits": {"max_steps": settings.max_steps, "max_run_tokens": settings.max_run_tokens,
                       "context_budget_tokens": settings.context_budget_tokens,
                       "min_write_confidence": settings.min_write_confidence,
                       "max_concurrent_runs": settings.max_concurrent_runs},
        }

    @app.get("/api/scenarios")
    def scenarios(_: str = Depends(require_auth)):
        return list_scenarios()

    @app.get("/api/tools")
    def tools(_: str = Depends(require_auth)):
        return tool_schemas()

    @app.post("/api/runs", status_code=201)
    async def create_run(body: CreateRun, actor: str = Depends(require_auth)):
        st = runtime.create_run(body.scenario_id)
        log.info(json.dumps({"event": "api.run_created", "run": st["run_id"], "actor": actor}))
        return runtime.public(st)

    @app.get("/api/runs")
    def list_runs(_: str = Depends(require_auth)):
        return store.list_runs()

    @app.get("/api/runs/{run_id}")
    def get_run(run_id: str, include_history: bool = False, _: str = Depends(require_auth)):
        return runtime.public(runtime.get(run_id), include_history)

    @app.get("/api/runs/{run_id}/context")
    def get_context(run_id: str, _: str = Depends(require_auth)):
        """Exactly what the model would see on its next step, rebuilt from the checkpoint."""
        messages, stats = build_context(runtime.get(run_id), settings)
        return {"system": SYSTEM_PROMPT, "messages": messages, "stats": stats, "tools": [t["name"] for t in tool_schemas()]}

    @app.get("/api/runs/{run_id}/events")
    def get_events(run_id: str, after: int = 0, _: str = Depends(require_auth)):
        runtime.get(run_id)
        return store.events_since(run_id, after)

    @app.get("/api/runs/{run_id}/stream")
    async def stream(run_id: str, request: Request, after: int = 0, _: str = Depends(require_auth)):
        runtime.get(run_id)
        last = request.headers.get("last-event-id")
        cursor = int(last) if last and last.isdigit() else after

        async def gen():
            nonlocal cursor
            yield "retry: 2000\n\n"
            idle = 0
            while not await request.is_disconnected():
                events = store.events_since(run_id, cursor)
                for e in events:
                    cursor = e["seq"]
                    yield f"id: {e['seq']}\ndata: {json.dumps(e, default=str)}\n\n"
                idle = 0 if events else idle + 1
                if idle and idle % 60 == 0:
                    yield ": keepalive\n\n"
                await asyncio.sleep(0.25)

        return StreamingResponse(gen(), media_type="text/event-stream",
                                 headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})

    # ---- operator actions (async: they schedule work on the event loop) ------------------------
    def _ok(run_id: str):
        return runtime.public(runtime.get(run_id))

    @app.post("/api/runs/{run_id}/approve")
    async def approve(run_id: str, body: Approve = Approve(), actor: str = Depends(require_auth)):
        runtime.approve(run_id, body.args, actor=actor)
        return _ok(run_id)

    @app.post("/api/runs/{run_id}/reject")
    async def reject(run_id: str, body: Reject = Reject(), actor: str = Depends(require_auth)):
        runtime.reject(run_id, body.feedback, actor=actor)
        return _ok(run_id)

    @app.post("/api/runs/{run_id}/message")
    async def message(run_id: str, body: Message, actor: str = Depends(require_auth)):
        runtime.message(run_id, body.text, actor=actor)
        return _ok(run_id)

    @app.post("/api/runs/{run_id}/pause")
    async def pause(run_id: str, _: str = Depends(require_auth)):
        runtime.pause(run_id)
        return _ok(run_id)

    @app.post("/api/runs/{run_id}/resume")
    async def resume(run_id: str, _: str = Depends(require_auth)):
        runtime.resume(run_id)
        return _ok(run_id)

    @app.post("/api/runs/{run_id}/cancel")
    async def cancel(run_id: str, _: str = Depends(require_auth)):
        runtime.cancel(run_id)
        return _ok(run_id)

    return app


def _build() -> FastAPI:
    try:
        return create_app()
    except Exception as e:  # ConfigError and friends: fail fast with one clear line
        raise SystemExit(f"Startup failed: {e}") from None


app = _build()
