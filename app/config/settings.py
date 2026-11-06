"""Runtime settings via pydantic-settings v2.

Every field can be overridden by an environment variable of the same name in
upper case (e.g. MAX_STEPS=40). A local .env file is read on startup if present;
real environment variables always win.
"""

from __future__ import annotations

from pathlib import Path
from typing import Literal

from pydantic import field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class ConfigError(Exception):
    """Invalid configuration. Raised at startup so a bad deploy fails fast."""


def load_dotenv(path: str = ".env") -> None:
    """Minimal .env loader used before Settings() so early imports see keys.

    pydantic-settings also reads .env; this keeps Scripts/tests that call
    load_dotenv() directly working.
    """
    import os

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


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        # .env is loaded explicitly in from_env() so Settings(db_path=...) in
        # tests is not polluted by a reviewer's local .env file.
        env_file=None,
        extra="ignore",
        case_sensitive=False,
    )

    db_path: str = "data/agent.db"
    # SQLAlchemy URL. Empty → derived from db_path (sqlite+aiosqlite).
    # Postgres example: postgresql+asyncpg://agent:agent@db:5432/agent
    database_url: str = ""

    llm_provider: Literal["auto", "gemini", "anthropic", "openai", "scripted"] = "auto"
    gemini_model: str = "gemini-3.5-flash"
    # Used automatically when the primary Gemini model returns 429/quota errors.
    gemini_fallback_model: str = "gemini-3.5-flash-lite"
    anthropic_model: str = "claude-sonnet-5-5"
    openai_model: str = "gpt-4.1"
    llm_timeout_s: float = 120.0
    llm_max_attempts: int = 4
    llm_backoff_s: float = 1.0
    llm_max_backoff_s: float = 60.0
    llm_max_output_tokens: int = 8192
    require_llm: bool = False

    max_steps: int = 25
    max_run_tokens: int = 400_000
    max_run_cost_usd: float = 1.0
    min_write_confidence: float = 0.5
    max_concurrent_runs: int = 10
    max_identical_tool_calls: int = 3
    budget_alert_ratio: float = 0.8
    # When True, exhausted step/token/cost budgets cancel the run instead of soft-stopping for resume.
    budget_hard_stop: bool = False

    context_budget_tokens: int = 24_000
    tool_output_max_chars: int = 6_000
    keep_recent_groups: int = 6

    tool_max_attempts: int = 3
    tool_backoff_s: float = 0.5
    tool_timeout_s: float = 10.0

    memory_ttl_days: int = 30

    cost_in_per_mtok: float = 0.5
    cost_out_per_mtok: float = 3.0

    api_token: str = ""
    # Comma-separated browser origins allowed to call the API (empty = same-origin only).
    cors_origins: str = ""
    max_request_bytes: int = 1_048_576
    log_format: Literal["text", "json"] = "text"
    log_level: str = "INFO"
    otlp_endpoint: str = ""

    # Langfuse (optional — no-op without keys)
    langfuse_public_key: str = ""
    langfuse_secret_key: str = ""
    langfuse_host: str = "https://cloud.langfuse.com"

    scripted_delay_s: float = 0.8

    # LangGraph checkpointer db (defaults beside app db)
    checkpoint_db_path: str = ""

    @field_validator("api_token")
    @classmethod
    def _token_len(cls, v: str) -> str:
        if v and len(v) < 16:
            raise ValueError("API_TOKEN must be at least 16 characters")
        return v

    @model_validator(mode="after")
    def _validate(self) -> Settings:
        problems: list[str] = []
        for name in (
            "max_steps",
            "max_run_tokens",
            "context_budget_tokens",
            "tool_output_max_chars",
            "max_concurrent_runs",
            "tool_max_attempts",
            "llm_max_attempts",
            "max_identical_tool_calls",
            "max_request_bytes",
        ):
            if getattr(self, name) <= 0:
                problems.append(f"{name.upper()} must be positive")
        if self.max_run_cost_usd < 0:
            problems.append("MAX_RUN_COST_USD must be >= 0 (0 disables the cost budget)")
        if not 0 < self.budget_alert_ratio <= 1:
            problems.append("BUDGET_ALERT_RATIO must be between 0 and 1")
        if not 0 <= self.min_write_confidence <= 1:
            problems.append("MIN_WRITE_CONFIDENCE must be between 0 and 1")
        if problems:
            raise ConfigError("; ".join(problems))
        return self

    def revalidate(self) -> None:
        """Re-run validators after in-place mutation (tests). Prefer model_validate for new code."""
        type(self).model_validate(self.model_dump())

    # Back-compat alias — not BaseModel.validate (different signature).
    def validate(self) -> None:  # type: ignore[override]
        self.revalidate()

    @classmethod
    def settings_customise_sources(
        cls, settings_cls, init_settings, env_settings, dotenv_settings, file_secret_settings
    ):
        # Only constructor kwargs by default — mirrors the old dataclass Settings(...).
        # from_env() applies environment variables explicitly.
        return (init_settings,)

    @classmethod
    def from_env(cls) -> Settings:
        import os

        load_dotenv()
        overrides: dict = {}
        for name, field in cls.model_fields.items():
            raw = os.getenv(name.upper())
            if raw is None or raw == "":
                continue
            default = field.default
            try:
                if field.annotation is bool or str(field.annotation) == "bool":
                    low = raw.strip().lower()
                    if low in ("1", "true", "yes", "on"):
                        overrides[name] = True
                    elif low in ("0", "false", "no", "off"):
                        overrides[name] = False
                    else:
                        raise ConfigError(f"{name.upper()}: expected true/false, got {raw!r}")
                elif hasattr(default, "__class__") and default is not None and type(default) in (int, float, str):
                    overrides[name] = type(default)(raw)
                else:
                    # Fall back to pydantic parsing via model_validate
                    overrides[name] = raw
            except ConfigError:
                raise
            except (ValueError, TypeError) as e:
                raise ConfigError(f"{name.upper()}: {e}") from None
        try:
            return cls(**overrides)
        except Exception as e:  # noqa: BLE001
            from pydantic import ValidationError

            if isinstance(e, ValidationError):
                msgs = []
                for err in e.errors():
                    loc = ".".join(str(x) for x in err.get("loc", ()))
                    msgs.append(f"{loc.upper()}: {err.get('msg')}" if loc else err.get("msg", str(e)))
                raise ConfigError("; ".join(msgs)) from None
            if isinstance(e, ConfigError):
                raise
            raise ConfigError(str(e)) from None

    def sqlalchemy_url(self) -> str:
        if self.database_url:
            return self.database_url
        path = self.db_path
        if path == ":memory:":
            return "sqlite+aiosqlite://"
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        return f"sqlite+aiosqlite:///{path}"

    def is_postgres(self) -> bool:
        return self.sqlalchemy_url().startswith("postgresql")

    def checkpoint_path(self) -> str:
        if self.checkpoint_db_path:
            return self.checkpoint_db_path
        if self.db_path == ":memory:":
            return ":memory:"
        p = Path(self.db_path)
        return str(p.with_name(p.stem + ".checkpoints" + p.suffix))
