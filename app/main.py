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
from typing import Any

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, PlainTextResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from .config import Settings
from .context import SYSTEM_PROMPT, build_context
from .llm import make_llm
from .logging_setup import configure_logging
from .mock_env import list_scenarios
from .observability.langfuse_tracer import configure_langfuse, shutdown_langfuse
from .observability.metrics import render_metrics, set_event_counts, set_run_counts
from .observability.tracing import configure_tracing, shutdown_tracing
from .runtime import InvalidInput, NotFound, RunStateError, Runtime, TooBusy
from .store import CheckpointConflict, Store
from .tools import tool_schemas

ROOT = Path(__file__).resolve().parent.parent
FRONTEND_DIST = ROOT / "frontend" / "dist"
STATIC = ROOT / "static"  # legacy fallback if frontend/dist missing
log = logging.getLogger("api")


class CreateRun(BaseModel):
    scenario_id: str = Field(max_length=100)


class Approve(BaseModel):
    args: dict[str, Any] | None = Field(default=None)


class Reject(BaseModel):
    feedback: str = Field(default="", max_length=2000)


class Message(BaseModel):
    text: str = Field(..., min_length=1, max_length=4000)


def create_app(settings: Settings | None = None, llm=None) -> FastAPI:
    settings = settings or Settings.from_env()
    configure_logging(settings.log_format, settings.log_level)
    store = Store(settings.db_path)
    runtime = Runtime(store, llm or make_llm(settings), settings)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        configure_tracing(settings.otlp_endpoint)
        configure_langfuse(settings.langfuse_public_key, settings.langfuse_secret_key, settings.langfuse_host)
        n = runtime.recover()
        if n:
            log.warning("marked %d in-flight run(s) as interrupted after restart", n)
        if not settings.api_token:
            log.warning("API_TOKEN is not set: the API, including production approvals, is unauthenticated. "
                        "Set API_TOKEN before exposing this service beyond localhost.")
        log.info("ready: provider=%s model=%s", runtime.llm.provider, runtime.llm.model)
        yield
        await runtime.shutdown()
        client = getattr(runtime.llm, "_client", None)
        if client is not None:
            try:
                await client.aclose()
            except Exception:  # noqa: BLE001
                pass
        shutdown_langfuse()
        shutdown_tracing()

    app = FastAPI(
        title="Incident Triage Agent",
        version="1.0.0",
        lifespan=lifespan,
        description=(
            "Durable incident-triage agent runtime: investigate alerts with tools, "
            "gate production changes behind operator approval (with confidence routing), "
            "checkpoint every step to SQLite, and stream the decision trace over SSE.\n\n"
            "When `API_TOKEN` is set, send `Authorization: Bearer <token>` "
            "(SSE may use `?token=` because EventSource cannot set headers). "
            "Optional `X-Operator` is recorded in the audit log."
        ),
    )
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

    @app.exception_handler(CheckpointConflict)
    async def _cas(_: Request, exc: CheckpointConflict):
        return JSONResponse({"detail": str(exc)}, status_code=409)

    origins = [o.strip() for o in (settings.cors_origins or "").split(",") if o.strip()]
    if origins:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=origins,
            allow_credentials=True,
            allow_methods=["GET", "POST", "OPTIONS"],
            allow_headers=["Authorization", "Content-Type", "X-Operator", "Last-Event-ID"],
        )

    @app.middleware("http")
    async def request_guards(request: Request, call_next):
        # Reject oversized bodies early (Content-Length). Multipart not used.
        cl = request.headers.get("content-length")
        if cl and cl.isdigit() and int(cl) > settings.max_request_bytes:
            return JSONResponse({"detail": f"Request body exceeds {settings.max_request_bytes} bytes"}, status_code=413)
        response = await call_next(request)
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("X-Frame-Options", "DENY")
        response.headers.setdefault("Referrer-Policy", "no-referrer")
        response.headers.setdefault("Permissions-Policy", "camera=(), microphone=(), geolocation=()")
        response.headers.setdefault(
            "Content-Security-Policy",
            "default-src 'self'; "
            "script-src 'self'; "
            "style-src 'self' 'unsafe-inline'; "
            "font-src 'self' data:; "
            "img-src 'self' data:; "
            "connect-src 'self'; "
            "frame-ancestors 'none'",
        )
        if request.url.path.startswith("/api/") or request.url.path in ("/healthz", "/readyz", "/metrics"):
            response.headers.setdefault("Cache-Control", "no-store")
        return response

    # Prefer Vite production build; fall back to legacy static/ during migration.
    assets_dir = FRONTEND_DIST / "assets" if (FRONTEND_DIST / "assets").is_dir() else None
    if assets_dir is not None:
        app.mount("/assets", StaticFiles(directory=assets_dir), name="assets")
    if STATIC.is_dir():
        app.mount("/static", StaticFiles(directory=STATIC), name="static")

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
        dist_index = FRONTEND_DIST / "index.html"
        if dist_index.is_file():
            return FileResponse(dist_index)
        # Unauthenticated shell so probes/auth tests and API-only boots still get 200.
        # Build the React app (`cd frontend && npm run build`) for the full console.

        return HTMLResponse(
            "<!doctype html><html><head><meta charset='utf-8'>"
            "<title>Incident triage</title></head><body>"
            "<h1>Incident triage API</h1>"
            "<p>Frontend not built. Run <code>cd frontend && npm ci && npm run build</code> "
            "or open the Vite dev server.</p>"
            "<p><a href='/healthz'>/healthz</a> · <a href='/readyz'>/readyz</a> · "
            "<a href='/api/health'>/api/health</a></p>"
            "</body></html>"
        )

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

    @app.get("/metrics")
    async def metrics():
        try:
            set_run_counts(runtime.store.status_counts())
            set_event_counts(runtime.store.event_counts())
        except Exception:  # noqa: BLE001
            pass
        body, ctype = render_metrics()
        return PlainTextResponse(body.decode("utf-8"), media_type=ctype)


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
            from .runtime import TERMINAL
            while not await request.is_disconnected():
                events = store.events_since(run_id, cursor)
                for e in events:
                    cursor = e["seq"]
                    yield f"id: {e['seq']}\ndata: {json.dumps(e, default=str)}\n\n"
                st = store.load(run_id) or {}
                if st.get("status") in TERMINAL and not events:
                    yield f"event: end\ndata: {json.dumps({"status": st.get("status")})}\n\n"
                    return
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
    async def approve(run_id: str, body: Approve | None = None, actor: str = Depends(require_auth)):
        body = body or Approve()
        runtime.approve(run_id, body.args, actor=actor)
        return _ok(run_id)

    @app.post("/api/runs/{run_id}/reject")
    async def reject(run_id: str, body: Reject | None = None, actor: str = Depends(require_auth)):
        body = body or Reject()
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
