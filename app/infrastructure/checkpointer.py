"""LangGraph checkpointer factory: SQLite by default, Postgres when DATABASE_URL says so."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from app.config import Settings


@asynccontextmanager
async def open_checkpointer(settings: Settings) -> AsyncIterator[Any]:
    if settings.is_postgres():
        # Convert SQLAlchemy async URL → psycopg conn string for the LG checkpointer.
        from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver

        url = settings.sqlalchemy_url()
        # postgresql+asyncpg://user:pass@host/db → postgresql://user:pass@host/db
        conn = url.replace("postgresql+asyncpg://", "postgresql://").replace("postgres+asyncpg://", "postgresql://")
        async with AsyncPostgresSaver.from_conn_string(conn) as saver:
            await saver.setup()
            yield saver
        return

    from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver

    path = settings.checkpoint_path()
    if path != ":memory:":
        Path(path).parent.mkdir(parents=True, exist_ok=True)
    async with AsyncSqliteSaver.from_conn_string(path) as saver:
        yield saver
