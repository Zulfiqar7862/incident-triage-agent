"""HTTP composition root: build settings, adapters, the run service, and the FastAPI app.

Routes live in ``app.presentation.http.routes``; this module only wires
dependencies, lifecycle hooks, and static assets. ASGI entrypoint: ``app.main:app``.
"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles

from app.config import Settings
from app.domain.ports import LLMPort
from app.infrastructure.llm_factory import make_llm
from app.infrastructure.store import Store
from app.observability.langfuse_tracer import configure_langfuse, shutdown_langfuse
from app.observability.logging_setup import configure_logging
from app.observability.tracing import configure_tracing, shutdown_tracing
from app.presentation.http.errors import install_error_handlers
from app.presentation.http.middleware import install_middleware
from app.presentation.http.routes import api, probes
from app.runtime import Runtime

ROOT = Path(__file__).resolve().parent.parent
FRONTEND_DIST = ROOT / "frontend" / "dist"
STATIC = ROOT / "static"  # legacy fallback if frontend/dist missing
log = logging.getLogger("api")

DESCRIPTION = (
    "Production agent runtime (not a chatbot wrapper): plans investigations, "
    "calls tools, recovers from failures, checkpoints durable state for resume, "
    "gates every production mutation behind operator approval, and streams the "
    "decision trace over SSE for live operator control.\n\n"
    "When `API_TOKEN` is set, send `Authorization: Bearer <token>` "
    "(SSE may use `?token=` because EventSource cannot set headers). "
    "Optional `X-Operator` is recorded in the audit log."
)


def create_app(settings: Settings | None = None, llm: LLMPort | None = None) -> FastAPI:
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
            log.warning(
                "API_TOKEN is not set: the API, including production approvals, is unauthenticated. "
                "Set API_TOKEN before exposing this service beyond localhost."
            )
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

    app = FastAPI(title="Incident Triage Agent", version="1.0.0", lifespan=lifespan, description=DESCRIPTION)
    app.state.runtime = runtime
    app.state.settings = settings

    install_error_handlers(app)
    install_middleware(app, settings)

    # Prefer the Vite production build; fall back to legacy static/.
    if (FRONTEND_DIST / "assets").is_dir():
        app.mount("/assets", StaticFiles(directory=FRONTEND_DIST / "assets"), name="assets")
    if STATIC.is_dir():
        app.mount("/static", StaticFiles(directory=STATIC), name="static")

    @app.get("/", include_in_schema=False)
    def index():
        dist_index = FRONTEND_DIST / "index.html"
        if dist_index.is_file():
            return FileResponse(dist_index)
        # Unauthenticated shell so probes/auth tests and API-only boots still get 200.
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

    app.include_router(probes)
    app.include_router(api)
    return app


def _build() -> FastAPI:
    try:
        return create_app()
    except Exception as e:  # ConfigError and friends: fail fast with one clear line
        raise SystemExit(f"Startup failed: {e}") from None


app = _build()
