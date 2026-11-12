"""FastAPI dependencies: the per-process run service, settings, and bearer auth."""

from __future__ import annotations

import hmac
import re

from fastapi import HTTPException, Request

from app.config import Settings
from app.runtime import Runtime


def get_runtime(request: Request) -> Runtime:
    return request.app.state.runtime


def get_settings(request: Request) -> Settings:
    return request.app.state.settings


def require_auth(request: Request) -> str:
    """Check the optional bearer token; return the operator name recorded in the audit log."""
    settings = get_settings(request)
    if settings.api_token:
        header = request.headers.get("authorization", "")
        token = header[7:] if header.lower().startswith("bearer ") else request.query_params.get("token", "")
        if not hmac.compare_digest(token.encode(), settings.api_token.encode()):
            raise HTTPException(401, "Missing or invalid API token", headers={"WWW-Authenticate": "Bearer"})
    name = re.sub(r"[^\w .@-]", "", request.headers.get("x-operator", ""))[:64].strip()
    return name or "operator"
