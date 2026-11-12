"""LLM adapters behind ``LLMPort`` (Strategy) and the registry-based factory."""

from app.domain.llm import LLMError, LLMResponse, LLMTransientError, ToolCall
from app.infrastructure.llm.anthropic import AnthropicLLM
from app.infrastructure.llm.factory import PROVIDERS, make_llm, resolve_provider
from app.infrastructure.llm.fallback import GeminiWithFallback
from app.infrastructure.llm.gemini import GEMINI_DUMMY_SIGNATURE, GeminiLLM, from_gemini, to_gemini
from app.infrastructure.llm.openai import OpenAILLM
from app.infrastructure.llm.scripted import ScriptedPolicy

__all__ = [
    "GEMINI_DUMMY_SIGNATURE",
    "PROVIDERS",
    "AnthropicLLM",
    "GeminiLLM",
    "GeminiWithFallback",
    "LLMError",
    "LLMResponse",
    "LLMTransientError",
    "OpenAILLM",
    "ScriptedPolicy",
    "ToolCall",
    "from_gemini",
    "make_llm",
    "resolve_provider",
    "to_gemini",
]
