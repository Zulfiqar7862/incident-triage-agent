"""Runtime settings. Every field can be overridden by an environment variable
of the same name in upper case (e.g. MAX_STEPS=40). A local .env file is read
on startup if present; real environment variables always win."""
from __future__ import annotations

import os
from dataclasses import dataclass, fields
from pathlib import Path


class ConfigError(Exception):
    """Invalid configuration. Raised at startup so a bad deploy fails fast."""


def load_dotenv(path: str = ".env") -> None:
    p = Path(path)
    if not p.exists():
        return
    for line in p.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        value = value.split(" #", 1)[0].strip().strip('"').strip("'")
        if value:
            os.environ.setdefault(key.strip(), value)


def _parse(raw: str, default):
    if isinstance(default, bool):
        if raw.strip().lower() in ("1", "true", "yes", "on"):
            return True
        if raw.strip().lower() in ("0", "false", "no", "off"):
            return False
        raise ConfigError(f"expected true/false, got {raw!r}")
    return type(default)(raw)


@dataclass
class Settings:
    db_path: str = "data/agent.db"

    # Model provider: auto | gemini | anthropic | openai | scripted
    llm_provider: str = "auto"
    gemini_model: str = "gemini-3.5-flash"
    anthropic_model: str = "claude-sonnet-5-5"
    openai_model: str = "gpt-4.1"
    llm_timeout_s: float = 120.0
    llm_max_attempts: int = 4
    llm_backoff_s: float = 1.0
    llm_max_backoff_s: float = 60.0  # cap on Retry-After / quota backoff
    llm_max_output_tokens: int = 8192
    # Refuse to start without a real model (no silent fallback to the offline policy).
    require_llm: bool = False

    # Run guardrails
    max_steps: int = 25
    max_run_tokens: int = 400_000
    max_run_cost_usd: float = 1.0
    min_write_confidence: float = 0.5
    max_concurrent_runs: int = 10
    max_identical_tool_calls: int = 3
    budget_alert_ratio: float = 0.8  # emit budget.alert when usage crosses this fraction

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

    # Cost estimate (USD per million tokens). Set to your model's current prices.
    cost_in_per_mtok: float = 0.5
    cost_out_per_mtok: float = 3.0

    # Security and operations
    api_token: str = ""          # when set, every /api request needs "Authorization: Bearer <token>"
    log_format: str = "text"     # text | json
    log_level: str = "INFO"
    otlp_endpoint: str = ""      # e.g. http://localhost:4318 — empty disables export

    # Offline scripted policy: delay per "LLM" call so the UI is watchable
    scripted_delay_s: float = 0.8

    @classmethod
    def from_env(cls) -> "Settings":
        load_dotenv()
        overrides = {}
        for f in fields(cls):
            raw = os.getenv(f.name.upper())
            if raw is not None and raw != "":
                try:
                    overrides[f.name] = _parse(raw, f.default)
                except (ValueError, ConfigError) as e:
                    raise ConfigError(f"{f.name.upper()}: {e}") from None
        settings = cls(**overrides)
        settings.validate()
        return settings

    def validate(self) -> None:
        problems = []
        if self.llm_provider not in ("auto", "gemini", "anthropic", "openai", "scripted"):
            problems.append(f"LLM_PROVIDER must be auto, gemini, anthropic, openai or scripted (got {self.llm_provider!r})")
        if self.log_format not in ("text", "json"):
            problems.append("LOG_FORMAT must be text or json")
        for name in ("max_steps", "max_run_tokens", "context_budget_tokens", "tool_output_max_chars",
                     "max_concurrent_runs", "tool_max_attempts", "llm_max_attempts",
                     "max_identical_tool_calls"):
            if getattr(self, name) <= 0:
                problems.append(f"{name.upper()} must be positive")
        if self.max_run_cost_usd < 0:
            problems.append("MAX_RUN_COST_USD must be >= 0 (0 disables the cost budget)")
        if not 0 < self.budget_alert_ratio <= 1:
            problems.append("BUDGET_ALERT_RATIO must be between 0 and 1")
        if not 0 <= self.min_write_confidence <= 1:
            problems.append("MIN_WRITE_CONFIDENCE must be between 0 and 1")
        if self.api_token and len(self.api_token) < 16:
            problems.append("API_TOKEN must be at least 16 characters")
        if problems:
            raise ConfigError("; ".join(problems))
