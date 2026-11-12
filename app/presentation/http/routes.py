"""HTTP routes. Each handler parses input, calls one use case, and maps the result
to a presentation view. No business rules live here.

Reads go to ``RunQueries`` and writes to ``RunService`` (CQRS-lite).
"""

from __future__ import annotations

import asyncio
import json
import logging
from collections.abc import AsyncIterator
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse, PlainTextResponse, StreamingResponse

from app.application.context import SYSTEM_PROMPT, build_context
from app.application.ports import TelemetryPort
from app.application.run_queries import RunQueries
from app.application.run_service import RunService
from app.application.tools import tool_schemas
from app.core.config import Settings
from app.domain.lifecycle import TERMINAL
from app.presentation.http.dependencies import get_queries, get_service, get_settings, get_telemetry, require_auth
from app.presentation.http.schemas import Approve, CreateRun, Message, Reject
from app.presentation.views.events import present_event
from app.presentation.views.run_view import present_run

log = logging.getLogger("api")

probes = APIRouter()
api = APIRouter(prefix="/api")

Queries = Annotated[RunQueries, Depends(get_queries)]
Commands = Annotated[RunService, Depends(get_service)]
Actor = Annotated[str, Depends(require_auth)]
AppSettings = Annotated[Settings, Depends(get_settings)]
Telemetry = Annotated[TelemetryPort, Depends(get_telemetry)]


# ---- health and metrics (unauthenticated: no run data) -----------------------------------
@probes.get("/healthz")
def healthz() -> dict[str, bool]:
    return {"ok": True}


@probes.get("/readyz", response_model=None)
def readyz(queries: Queries) -> dict[str, Any] | JSONResponse:
    try:
        queries.ping()
    except Exception as e:  # noqa: BLE001 - readiness reports any DB failure as 503
        return JSONResponse({"ok": False, "db": str(e)}, status_code=503)
    return {"ok": True, "llm": queries.model_info["provider"]}


@probes.get("/metrics")
async def metrics(queries: Queries, telemetry: Telemetry) -> PlainTextResponse:
    try:
        runs, events = queries.health_counts()
    except Exception:  # noqa: BLE001 - a scrape must still return the process metrics
        runs, events = {}, {}
    body, ctype = telemetry.export(runs, events)
    return PlainTextResponse(body.decode("utf-8"), media_type=ctype)


# ---- catalog ---------------------------------------------------------------------------
@api.get("/health")
def health(_: Actor, queries: Queries, settings: AppSettings) -> dict[str, Any]:
    return {
        "ok": True,
        "auth": bool(settings.api_token),
        "llm": queries.model_info,
        "limits": {
            "max_steps": settings.max_steps,
            "max_run_tokens": settings.max_run_tokens,
            "context_budget_tokens": settings.context_budget_tokens,
            "min_write_confidence": settings.min_write_confidence,
            "max_concurrent_runs": settings.max_concurrent_runs,
        },
    }


@api.get("/scenarios")
def scenarios(_: Actor, queries: Queries) -> list[dict]:
    return queries.list_scenarios()


@api.get("/tools")
def tools(_: Actor) -> list[dict]:
    return tool_schemas()


# ---- runs: reads -----------------------------------------------------------------------
@api.get("/runs")
def list_runs(_: Actor, queries: Queries) -> list[dict]:
    return queries.list_runs()


@api.get("/runs/{run_id}")
def get_run(run_id: str, _: Actor, queries: Queries, include_history: bool = False) -> dict[str, Any]:
    return present_run(queries, queries.get(run_id), include_history)


@api.get("/runs/{run_id}/context")
def get_context(run_id: str, _: Actor, queries: Queries, settings: AppSettings) -> dict[str, Any]:
    """Exactly what the model would see on its next step, rebuilt from the checkpoint."""
    messages, stats = build_context(queries.get(run_id), settings)
    return {
        "system": SYSTEM_PROMPT,
        "messages": messages,
        "stats": stats,
        "tools": [t["name"] for t in tool_schemas()],
    }


@api.get("/runs/{run_id}/events")
def get_events(run_id: str, _: Actor, queries: Queries, after: int = 0) -> list[dict]:
    st = queries.get(run_id)
    return [present_event(event, st) for event in queries.events_since(run_id, after)]


@api.get("/runs/{run_id}/stream")
async def stream(run_id: str, request: Request, _: Actor, queries: Queries, after: int = 0) -> StreamingResponse:
    """Server-Sent Events over the append-only event log (Observer). Resumes from Last-Event-ID."""
    queries.get(run_id)
    last = request.headers.get("last-event-id")
    cursor = int(last) if last and last.isdigit() else after

    async def gen() -> AsyncIterator[str]:
        nonlocal cursor
        yield "retry: 2000\n\n"
        idle = 0
        while not await request.is_disconnected():
            events = queries.events_since(run_id, cursor)
            current = queries.find(run_id) or {}
            for raw in events:
                e = present_event(raw, current)
                cursor = e["seq"]
                yield f"id: {e['seq']}\ndata: {json.dumps(e, default=str)}\n\n"
            st = queries.find(run_id) or {}
            if st.get("status") in TERMINAL and not events:
                yield f"event: end\ndata: {json.dumps({'status': st.get('status')})}\n\n"
                return
            idle = 0 if events else idle + 1
            if idle and idle % 60 == 0:
                yield ": keepalive\n\n"
            await asyncio.sleep(0.25)

    return StreamingResponse(
        gen(), media_type="text/event-stream", headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"}
    )


@api.get("/runs/{run_id}/events/verify")
def verify_events(run_id: str, _: Actor, queries: Queries) -> dict:
    """Recompute the per-run SHA-256 event hash chain (tamper detection)."""
    return queries.verify_events(run_id)


# ---- runs: commands (async: they schedule work on the event loop) ----------------------------
@api.post("/runs", status_code=201)
async def create_run(body: CreateRun, actor: Actor, commands: Commands, queries: Queries) -> dict[str, Any]:
    st = commands.create_run(body.scenario_id)
    log.info(json.dumps({"event": "api.run_created", "run": st["run_id"], "actor": actor}))
    return present_run(queries, st)


@api.post("/runs/{run_id}/approve")
async def approve(
    run_id: str, actor: Actor, commands: Commands, queries: Queries, body: Approve | None = None
) -> dict[str, Any]:
    commands.approve(run_id, (body or Approve()).args, actor=actor)
    return present_run(queries, queries.get(run_id))


@api.post("/runs/{run_id}/reject")
async def reject(
    run_id: str, actor: Actor, commands: Commands, queries: Queries, body: Reject | None = None
) -> dict[str, Any]:
    commands.reject(run_id, (body or Reject()).feedback, actor=actor)
    return present_run(queries, queries.get(run_id))


@api.post("/runs/{run_id}/message")
async def message(run_id: str, body: Message, actor: Actor, commands: Commands, queries: Queries) -> dict[str, Any]:
    commands.message(run_id, body.text, actor=actor)
    return present_run(queries, queries.get(run_id))


@api.post("/runs/{run_id}/pause")
async def pause(run_id: str, _: Actor, commands: Commands, queries: Queries) -> dict[str, Any]:
    commands.pause(run_id)
    return present_run(queries, queries.get(run_id))


@api.post("/runs/{run_id}/resume")
async def resume(run_id: str, _: Actor, commands: Commands, queries: Queries) -> dict[str, Any]:
    commands.resume(run_id)
    return present_run(queries, queries.get(run_id))


@api.post("/runs/{run_id}/cancel")
async def cancel(run_id: str, _: Actor, commands: Commands, queries: Queries) -> dict[str, Any]:
    commands.cancel(run_id)
    return present_run(queries, queries.get(run_id))


@api.post("/emergency-stop")
async def emergency_stop(actor: Actor, commands: Commands) -> dict[str, Any]:
    """Cancel every non-terminal run (fleet-wide kill switch)."""
    return {"ok": True, "actor": actor, **commands.emergency_stop()}
