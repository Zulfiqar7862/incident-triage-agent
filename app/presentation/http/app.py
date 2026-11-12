"""FastAPI application factory: routers, error mapping, middleware, static assets.

Receives an already-wired container; it never chooses adapters itself.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Protocol

from fastapi import FastAPI
from fastapi.responses import FileResponse, HTMLResponse, Response
from fastapi.staticfiles import StaticFiles

from app.application.ports import TelemetryPort
from app.application.run_queries import RunQueries
from app.application.run_service import RunService
from app.core.config import Settings
from app.presentation.http.errors import install_error_handlers
from app.presentation.http.middleware import install_middleware
from app.presentation.http.routes import api, probes

ROOT = Path(__file__).resolve().parents[3]
FRONTEND_DIST = ROOT / "frontend" / "dist"
STATIC = ROOT / "static"  # legacy fallback if frontend/dist is missing

DESCRIPTION = (
    "Production agent runtime (not a chatbot wrapper): plans investigations, "
    "calls tools, recovers from failures, checkpoints durable state for resume, "
    "gates every production mutation behind operator approval, and streams the "
    "decision trace over SSE for live operator control.\n\n"
    "When `API_TOKEN` is set, send `Authorization: Bearer <token>` "
    "(SSE may use `?token=` because EventSource cannot set headers). "
    "Optional `X-Operator` is recorded in the audit log."
)

NOT_BUILT_PAGE = (
    "<!doctype html><html><head><meta charset='utf-8'>"
    "<title>Incident triage</title></head><body>"
    "<h1>Incident triage API</h1>"
    "<p>Frontend not built. Run <code>cd frontend && npm ci && npm run build</code> "
    "or open the Vite dev server.</p>"
    "<p><a href='/healthz'>/healthz</a> · <a href='/readyz'>/readyz</a> · "
    "<a href='/api/health'>/api/health</a></p>"
    "</body></html>"
)


class AppContainer(Protocol):
    """What the HTTP layer needs from the composition root."""

    settings: Settings
    service: RunService
    telemetry: TelemetryPort

    @property
    def queries(self) -> RunQueries: ...

    async def start(self) -> None: ...

    async def aclose(self) -> None: ...


def create_http_app(container: AppContainer) -> FastAPI:
    """Build the FastAPI app around a wired container."""

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        await container.start()
        yield
        await container.aclose()

    app = FastAPI(title="Incident Triage Agent", version="1.0.0", lifespan=lifespan, description=DESCRIPTION)
    app.state.service = container.service
    app.state.queries = container.queries
    app.state.settings = container.settings
    app.state.telemetry = container.telemetry
    install_error_handlers(app)
    install_middleware(app, container.settings)
    _mount_frontend(app)
    app.include_router(probes)
    app.include_router(api)
    return app


def _mount_frontend(app: FastAPI) -> None:
    """Serve the Vite build when present; otherwise an unauthenticated API landing page."""
    if (FRONTEND_DIST / "assets").is_dir():
        app.mount("/assets", StaticFiles(directory=FRONTEND_DIST / "assets"), name="assets")
    if STATIC.is_dir():
        app.mount("/static", StaticFiles(directory=STATIC), name="static")

    @app.get("/", include_in_schema=False)
    def index() -> Response:
        dist_index = FRONTEND_DIST / "index.html"
        if dist_index.is_file():
            return FileResponse(dist_index)
        return HTMLResponse(NOT_BUILT_PAGE)
