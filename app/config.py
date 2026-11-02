"""Runtime settings. Every field can be overridden by an environment variable
of the same name in upper case (e.g. MAX_STEPS=40). A local .env file is read
on startup if present."""
from __future__ import annotations

import os
from dataclasses import dataclass, fields
from pathlib import Path


def load_dotenv(path: str = ".env") -> None:
    p = Path(path)
    if not p.exists():
        return
    for line in p.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        value = value.strip().strip('"').strip("'")
        if value:
            os.environ.setdefault(key.strip(), value)


@dataclass
class Settings:
    db_path: str = "data/agent.db"
    llm_provider: str = "auto"  # auto | anthropic | openai | scripted
    anthropic_model: str = "claude-sonnet-5-5"
    openai_model: str = "gpt-4.1"
    llm_timeout_s: float = 90.0
    llm_max_attempts: int = 4
    llm_backoff_s: float = 1.0

    # Run guardrails
    max_steps: int = 25
    max_run_tokens: int = 400_000
    min_write_confidence: float = 0.5

    # Context engineering
    context_budget_tokens: int = 24_000
    tool_output_max_chars: int = 6_000
    keep_recent_groups: int = 6

    # Tool execution
    tool_max_attempts: int = 3
    tool_backoff_s: float = 0.5
    tool_timeout_s: float = 10.0

    # Long-term memory
    memory_ttl_days: int = 30

    # Cost estimate (USD per million tokens)
    cost_in_per_mtok: float = 3.0
    cost_out_per_mtok: float = 15.0

    # Offline scripted policy: delay per "LLM" call so the UI is watchable
    scripted_delay_s: float = 0.8

    @classmethod
    def from_env(cls) -> "Settings":
        load_dotenv()
        overrides = {}
        for f in fields(cls):
            raw = os.getenv(f.name.upper())
            if raw is not None and raw != "":
                overrides[f.name] = type(f.default)(raw)
        return cls(**overrides)
