"""HTTP API: agent runtime, tools, run state, and a live event stream (SSE)."""
from __future__ import annotations

import asyncio
import json
import logging
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, Optional

from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from pydantic import BaseModel

from .config import Settings
from .context import SYSTEM_PROMPT, build_context
from .llm import make_llm
from .mock_env import list_scenarios
from .runtime import InvalidInput, NotFound, Runtime, RunStateError
from .store import Store
from .tools import tool_schemas

STATIC = Path(__file__).resolve().parent.parent / "static"


class CreateRun(BaseModel):
    scenario_id: str


class Approve(BaseModel):
    args: Optional[dict[str, Any]] = None


class Reject(BaseModel):
    feedback: str = ""


class Message(BaseModel):
    text: str


def create_app(settings: Settings | None = None, llm=None) -> FastAPI:
    settings = settings or Settings.from_env()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    store = Store(settings.db_path)
    runtime = Runtime(store, llm or make_llm(settings), settings)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        n = runtime.recover()
        if n:
            logging.getLogger("agent").warning("marked %d in-flight run(s) as interrupted", n)
        yield

    app = FastAPI(title="Incident Triage Agent", version="0.1.0", lifespan=lifespan)
    app.state.runtime = runtime

    @app.exception_handler(NotFound)
    async def _not_found(_: Request, exc: NotFound):
        return JSONResponse({"detail": str(exc)}, status_code=404)

    @app.exception_handler(RunStateError)
    async def _conflict(_: Request, exc: RunStateError):
        return JSONResponse({"detail": str(exc)}, status_code=409)

    @app.exception_handler(InvalidInput)
    async def _invalid(_: Request, exc: InvalidInput):
        return JSONResponse({"detail": str(exc)}, status_code=422)

    # ---- UI + metadata ---------------------------------------------------------------------
    @app.get("/", include_in_schema=False)
    def index():
        return FileResponse(STATIC / "index.html")

    @app.get("/api/health")
    def health():
        return {
            "ok": True,
            "llm": {"provider": runtime.llm.provider, "model": runtime.llm.model},
            "limits": {"max_steps": settings.max_steps, "max_run_tokens": settings.max_run_tokens,
                       "context_budget_tokens": settings.context_budget_tokens,
                       "min_write_confidence": settings.min_write_confidence},
        }

    @app.get("/api/scenarios")
    def scenarios():
        return list_scenarios()

    @app.get("/api/tools")
    def tools():
        return tool_schemas()

    # ---- runs ---------------------------------------------------------------------------------
    @app.post("/api/runs", status_code=201)
    async def create_run(body: CreateRun):
        return runtime.public(runtime.create_run(body.scenario_id))

    @app.get("/api/runs")
    def list_runs():
        return store.list_runs()

    @app.get("/api/runs/{run_id}")
    def get_run(run_id: str, include_history: bool = False):
        return runtime.public(runtime.get(run_id), include_history)

    @app.get("/api/runs/{run_id}/context")
    def get_context(run_id: str):
        """Exactly what the model would see on its next step, rebuilt from the checkpoint."""
        messages, stats = build_context(runtime.get(run_id), settings)
        return {"system": SYSTEM_PROMPT, "messages": messages, "stats": stats, "tools": [t["name"] for t in tool_schemas()]}

    @app.get("/api/runs/{run_id}/events")
    def get_events(run_id: str, after: int = 0):
        runtime.get(run_id)
        return store.events_since(run_id, after)

    @app.get("/api/runs/{run_id}/stream")
    async def stream(run_id: str, request: Request, after: int = 0):
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

    # ---- operator actions (async: they schedule work on the event loop) -------------------------------------------------------------------
    def _ok(run_id: str):
        return runtime.public(runtime.get(run_id))

    @app.post("/api/runs/{run_id}/approve")
    async def approve(run_id: str, body: Approve = Approve()):
        runtime.approve(run_id, body.args)
        return _ok(run_id)

    @app.post("/api/runs/{run_id}/reject")
    async def reject(run_id: str, body: Reject = Reject()):
        runtime.reject(run_id, body.feedback)
        return _ok(run_id)

    @app.post("/api/runs/{run_id}/message")
    async def message(run_id: str, body: Message):
        runtime.message(run_id, body.text)
        return _ok(run_id)

    @app.post("/api/runs/{run_id}/pause")
    async def pause(run_id: str):
        runtime.pause(run_id)
        return _ok(run_id)

    @app.post("/api/runs/{run_id}/resume")
    async def resume(run_id: str):
        runtime.resume(run_id)
        return _ok(run_id)

    @app.post("/api/runs/{run_id}/cancel")
    async def cancel(run_id: str):
        runtime.cancel(run_id)
        return _ok(run_id)

    return app


app = create_app()
