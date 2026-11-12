"""LLM Strategy factory backed by a provider registry (no if/elif on provider names).

``LLM_PROVIDER=auto`` picks the first provider whose API key is present, in the
order of ``AUTO_ORDER``; with no key the offline scripted policy runs.
"""

from __future__ import annotations

import os
from collections.abc import Callable

import httpx

from app.core.config import ConfigError, Settings
from app.domain.ports import LLMPort
from app.infrastructure.llm.anthropic import AnthropicLLM
from app.infrastructure.llm.fallback import GeminiWithFallback
from app.infrastructure.llm.gemini import GeminiLLM
from app.infrastructure.llm.openai import OpenAILLM
from app.infrastructure.llm.scripted import ScriptedPolicy

ProviderBuilder = Callable[[Settings, httpx.AsyncBaseTransport | None], LLMPort]


def _gemini_key() -> str:
    return os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY") or ""


def _require(env_value: str, provider: str, env_name: str) -> str:
    if not env_value:
        raise ConfigError(f"LLM_PROVIDER={provider} but {env_name} is not set")
    return env_value


def _build_gemini(settings: Settings, transport: httpx.AsyncBaseTransport | None) -> LLMPort:
    key = _require(_gemini_key(), "gemini", "GEMINI_API_KEY")
    timeout, max_out = settings.llm_timeout_s, settings.llm_max_output_tokens
    primary = GeminiLLM(settings.gemini_model, key, timeout, max_out, transport)
    fallback_name = (settings.gemini_fallback_model or "").strip()
    if fallback_name and fallback_name != settings.gemini_model:
        return GeminiWithFallback(primary, GeminiLLM(fallback_name, key, timeout, max_out, transport))
    return primary


def _build_anthropic(settings: Settings, transport: httpx.AsyncBaseTransport | None) -> LLMPort:
    key = _require(os.getenv("ANTHROPIC_API_KEY", ""), "anthropic", "ANTHROPIC_API_KEY")
    return AnthropicLLM(
        settings.anthropic_model, key, settings.llm_timeout_s, settings.llm_max_output_tokens, transport
    )


def _build_openai(settings: Settings, transport: httpx.AsyncBaseTransport | None) -> LLMPort:
    key = _require(os.getenv("OPENAI_API_KEY", ""), "openai", "OPENAI_API_KEY")
    return OpenAILLM(settings.openai_model, key, settings.llm_timeout_s, settings.llm_max_output_tokens, transport)


def _build_scripted(settings: Settings, transport: httpx.AsyncBaseTransport | None) -> LLMPort:
    return ScriptedPolicy(delay_s=settings.scripted_delay_s)


PROVIDERS: dict[str, ProviderBuilder] = {
    "gemini": _build_gemini,
    "anthropic": _build_anthropic,
    "openai": _build_openai,
    "scripted": _build_scripted,
}
"""Registry: provider name -> builder. Add a provider by adding one entry."""

AUTO_ORDER: tuple[tuple[str, Callable[[], str]], ...] = (
    ("gemini", _gemini_key),
    ("anthropic", lambda: os.getenv("ANTHROPIC_API_KEY", "")),
    ("openai", lambda: os.getenv("OPENAI_API_KEY", "")),
)


def resolve_provider(settings: Settings) -> str:
    """Concrete provider name for ``settings.llm_provider`` (resolving ``auto``)."""
    provider: str = settings.llm_provider
    if provider == "auto":
        provider = next((name for name, key in AUTO_ORDER if key()), "scripted")
    if provider == "scripted" and settings.require_llm:
        raise ConfigError(
            "REQUIRE_LLM is true but no model is configured. Set GEMINI_API_KEY (or another provider's key)."
        )
    return provider


def make_llm(settings: Settings, transport: httpx.AsyncBaseTransport | None = None) -> LLMPort:
    """Build the configured ``LLMPort`` Strategy."""
    provider = resolve_provider(settings)
    builder = PROVIDERS.get(provider)
    if builder is None:
        raise ConfigError(f"Unknown LLM_PROVIDER '{provider}'. Choose one of: auto, {', '.join(PROVIDERS)}")
    return builder(settings, transport)
