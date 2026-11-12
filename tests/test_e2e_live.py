"""Opt-in live Gemini smoke (skipped in CI without GEMINI_API_KEY)."""

from __future__ import annotations

import os
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


def _load_dotenv() -> None:
    env = ROOT / ".env"
    if not env.exists():
        return
    for line in env.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, _, v = line.partition("=")
        v = v.split(" #", 1)[0].strip().strip('"').strip("'")
        if v:
            os.environ.setdefault(k.strip(), v)


_load_dotenv()
pytestmark = pytest.mark.live


@pytest.mark.skipif(
    not (os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")),
    reason="no GEMINI_API_KEY",
)
def test_live_gemini_health_and_one_run(tmp_path):
    """Spin a short live run to awaiting_approval (or completed) then cancel."""
    import time

    from app.core.config import Settings, load_dotenv
    from app.infrastructure.llm import make_llm
    from app.main import create_app
    from fastapi.testclient import TestClient

    load_dotenv()
    os.environ.setdefault("GEMINI_MODEL", "gemini-3.5-flash-lite")
    settings = Settings.from_env()
    settings = settings.model_copy(
        update={
            "db_path": str(tmp_path / "live.db"),
            "gemini_model": os.environ.get("GEMINI_MODEL", "gemini-3.5-flash-lite"),
            "require_llm": True,
            "llm_provider": "gemini",
            "tool_backoff_s": 0.05,
            "max_steps": 12,
        }
    )
    llm = make_llm(settings)
    with TestClient(create_app(settings, llm=llm)) as c:
        h = c.get("/api/health").json()
        assert h["llm"]["provider"] == "gemini"
        rid = c.post("/api/runs", json={"scenario_id": "upstream-oom"}, headers={"X-Operator": "live-test"}).json()[
            "run_id"
        ]
        st = None
        for _ in range(300):
            st = c.get(f"/api/runs/{rid}").json()
            if st["status"] in {"awaiting_approval", "completed", "failed", "needs_attention"}:
                break
            time.sleep(0.4)
        assert st is not None
        assert st["status"] in {"awaiting_approval", "completed", "failed", "needs_attention"}, st
        if st["status"] not in {"completed", "failed", "cancelled"}:
            c.post(f"/api/runs/{rid}/cancel")
