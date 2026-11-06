"""Re-export LLM Strategy factory for a clear infrastructure entry point."""

from app.llm.providers import make_llm, resolve_provider

__all__ = ["make_llm", "resolve_provider"]
