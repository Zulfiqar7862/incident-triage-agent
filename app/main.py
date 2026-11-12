"""ASGI entrypoint (``uvicorn app.main:app``): build the container, then the HTTP app."""

from __future__ import annotations

from fastapi import FastAPI

from app.core.config import Settings
from app.core.container import build_container
from app.domain.ports import LLMPort
from app.presentation.http.app import create_http_app


def create_app(settings: Settings | None = None, llm: LLMPort | None = None) -> FastAPI:
    """App factory used by uvicorn, tests, and scripts."""
    return create_http_app(build_container(settings, llm))


def _build() -> FastAPI:
    try:
        return create_app()
    except Exception as e:  # noqa: BLE001 - ConfigError and friends: fail fast with one clear line
        raise SystemExit(f"Startup failed: {e}") from None


app = _build()
