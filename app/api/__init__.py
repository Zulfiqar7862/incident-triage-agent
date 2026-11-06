"""HTTP API package. The ASGI entrypoint remains app.main:app."""

from app.main import create_app

__all__ = ["create_app"]
