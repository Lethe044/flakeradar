from __future__ import annotations

from typing import Optional

from ..config import Config
from .anthropic_provider import AnthropicProvider
from .base import LLMError, LLMProvider
from .gemini_provider import GeminiProvider
from .groq_provider import GroqProvider
from .ollama_provider import OllamaProvider
from .openai_provider import OpenAIProvider

_PROVIDERS = {
    "groq": GroqProvider,
    "gemini": GeminiProvider,
    "ollama": OllamaProvider,
    "openai": OpenAIProvider,
    "anthropic": AnthropicProvider,
}

__all__ = ["LLMError", "LLMProvider", "build_provider", "provider_names"]


def provider_names() -> list:
    return sorted(_PROVIDERS.keys())


def build_provider(config: Config) -> Optional[LLMProvider]:
    """Instantiate the configured provider, or None if AI analysis is disabled."""
    provider_key = (config.llm_provider or "none").lower()
    if provider_key in ("none", "", "off", "disabled"):
        return None
    cls = _PROVIDERS.get(provider_key)
    if cls is None:
        raise LLMError(
            f"Unknown llm_provider '{provider_key}'. Choose one of: none, {', '.join(provider_names())}"
        )
    return cls(
        api_key=config.llm_api_key or "",
        model=config.default_llm_model(),
        base_url=config.llm_base_url or "",
        timeout=config.llm_timeout,
    )
