"""HTTP routes. Each handler validates input, calls one run-service method, and
returns a presentation view. No business rules live here."""

from __future__ import annotations

import asyncio
import json
import logging

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse, PlainTextResponse, StreamingResponse

from app.config import Settings
from app.context import SYSTEM_PROMPT, build_context
from app.domain.lifecycle import TERMINAL
from app.observability.metrics import render_metrics, set_event_counts, set_run_counts
from app.presentation.http.dependencies import get_runtime, get_settings, require_auth
from app.presentation.http.schemas import Approve, CreateRun, Message, Reject
from app.presentation.operator import present_event
from app.presentation.run_view import present_run
from app.runtime import Runtime
from app.tools import tool_schemas

log = logging.getLogger("api")

probes = APIRouter()
api = APIRouter(prefix="/api")


# ---- health and metrics (unauthenticated: no run data) -----------------------------------
@probes.get("/healthz")
def healthz():
    return {"ok": True}


@probes.get("/readyz")
def readyz(runtime: Runtime = Depends(get_runtime)):
    try:
        runtime.ping()
    except Exception as e:  # noqa: BLE001
        return JSONResponse({"ok": False, "db": str(e)}, status_code=503)
    return {"ok": True, "llm": runtime.llm.provider}


@probes.get("/metrics")
async def metrics(runtime: Runtime = Depends(get_runtime)):
    try:
        runs, events = runtime.health_counts()
        set_run_counts(runs)
        set_event_counts(events)
    except Exception:  # noqa: BLE001
        pass
    body, ctype = render_metrics()
    return PlainTextResponse(body.decode("utf-8"), media_type=ctype)


# ---- catalog ---------------------------------------------------------------------------
@api.get("/health")
def health(
    _: str = Depends(require_auth),
    runtime: Runtime = Depends(get_runtime),
    settings: Settings = Depends(get_settings),
):
    return {
        "ok": True,
        "auth": bool(settings.api_token),
        "llm": {"provider": runtime.llm.provider, "model": runtime.llm.model},
        "limits": {
            "max_steps": settings.max_steps,
            "max_run_tokens": settings.max_run_tokens,
            "context_budget_tokens": settings.context_budget_tokens,
            "min_write_confidence": settings.min_write_confidence,
            "max_concurrent_runs": settings.max_concurrent_runs,
        },
    }


@api.get("/scenarios")
def scenarios(_: str = Depends(require_auth), runtime: Runtime = Depends(get_runtime)):
    return runtime.list_scenarios()


@api.get("/tools")
def tools(_: str = Depends(require_auth)):
    return tool_schemas()


# ---- runs ------------------------------------------------------------------------------
@api.post("/runs", status_code=201)
async def create_run(body: CreateRun, actor: str = Depends(require_auth), runtime: Runtime = Depends(get_runtime)):
    st = runtime.create_run(body.scenario_id)
    log.info(json.dumps({"event": "api.run_created", "run": st["run_id"], "actor": actor}))
    return present_run(runtime, st)


@api.get("/runs")
def list_runs(_: str = Depends(require_auth), runtime: Runtime = Depends(get_runtime)):
    return runtime.list_runs()


@api.get("/runs/{run_id}")
def get_run(
    run_id: str, include_history: bool = False, _: str = Depends(require_auth), runtime: Runtime = Depends(get_runtime)
):
    return present_run(runtime, runtime.get(run_id), include_history)


@api.get("/runs/{run_id}/context")
def get_context(
    run_id: str,
    _: str = Depends(require_auth),
    runtime: Runtime = Depends(get_runtime),
    settings: Settings = Depends(get_settings),
):
    """Exactly what the model would see on its next step, rebuilt from the checkpoint."""
    messages, stats = build_context(runtime.get(run_id), settings)
    return {
        "system": SYSTEM_PROMPT,
        "messages": messages,
        "stats": stats,
        "tools": [t["name"] for t in tool_schemas()],
    }


@api.get("/runs/{run_id}/events")
def get_events(run_id: str, after: int = 0, _: str = Depends(require_auth), runtime: Runtime = Depends(get_runtime)):
    st = runtime.get(run_id)
    return [present_event(event, st) for event in runtime.events_since(run_id, after)]


@api.get("/runs/{run_id}/stream")
async def stream(
    run_id: str,
    request: Request,
    after: int = 0,
    _: str = Depends(require_auth),
    runtime: Runtime = Depends(get_runtime),
):
    """Server-Sent Events over the append-only event log (Observer). Resumes from Last-Event-ID."""
    runtime.get(run_id)
    last = request.headers.get("last-event-id")
    cursor = int(last) if last and last.isdigit() else after

    async def gen():
        nonlocal cursor
        yield "retry: 2000\n\n"
        idle = 0
        while not await request.is_disconnected():
            events = runtime.events_since(run_id, cursor)
            current = runtime.store.load(run_id) or {}
            for raw in events:
                e = present_event(raw, current)
                cursor = e["seq"]
                yield f"id: {e['seq']}\ndata: {json.dumps(e, default=str)}\n\n"
            st = runtime.store.load(run_id) or {}
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
def verify_events(run_id: str, _: str = Depends(require_auth), runtime: Runtime = Depends(get_runtime)):
    """Recompute the per-run SHA-256 event hash chain (tamper detection)."""
    return runtime.verify_events(run_id)


# ---- operator actions (async: they schedule work on the event loop) ------------------------
@api.post("/runs/{run_id}/approve")
async def approve(
    run_id: str,
    body: Approve | None = None,
    actor: str = Depends(require_auth),
    runtime: Runtime = Depends(get_runtime),
):
    runtime.approve(run_id, (body or Approve()).args, actor=actor)
    return present_run(runtime, runtime.get(run_id))


@api.post("/runs/{run_id}/reject")
async def reject(
    run_id: str, body: Reject | None = None, actor: str = Depends(require_auth), runtime: Runtime = Depends(get_runtime)
):
    runtime.reject(run_id, (body or Reject()).feedback, actor=actor)
    return present_run(runtime, runtime.get(run_id))


@api.post("/runs/{run_id}/message")
async def message(
    run_id: str, body: Message, actor: str = Depends(require_auth), runtime: Runtime = Depends(get_runtime)
):
    runtime.message(run_id, body.text, actor=actor)
    return present_run(runtime, runtime.get(run_id))


@api.post("/runs/{run_id}/pause")
async def pause(run_id: str, _: str = Depends(require_auth), runtime: Runtime = Depends(get_runtime)):
    runtime.pause(run_id)
    return present_run(runtime, runtime.get(run_id))


@api.post("/runs/{run_id}/resume")
async def resume(run_id: str, _: str = Depends(require_auth), runtime: Runtime = Depends(get_runtime)):
    runtime.resume(run_id)
    return present_run(runtime, runtime.get(run_id))


@api.post("/runs/{run_id}/cancel")
async def cancel(run_id: str, _: str = Depends(require_auth), runtime: Runtime = Depends(get_runtime)):
    runtime.cancel(run_id)
    return present_run(runtime, runtime.get(run_id))


@api.post("/emergency-stop")
async def emergency_stop(actor: str = Depends(require_auth), runtime: Runtime = Depends(get_runtime)):
    """Cancel every non-terminal run (fleet-wide kill switch)."""
    return {"ok": True, "actor": actor, **runtime.emergency_stop()}
