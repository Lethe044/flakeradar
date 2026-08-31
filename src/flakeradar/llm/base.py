"""Common interface every LLM provider implements."""

from __future__ import annotations

from abc import ABC, abstractmethod


class LLMError(RuntimeError):
    """Raised when a provider call fails (network, auth, bad response, etc.)."""


class LLMProvider(ABC):
    name: str = "base"

    def __init__(self, api_key: str = "", model: str = "", base_url: str = "", timeout: float = 30.0):
        self.api_key = api_key
        self.model = model
        self.base_url = base_url
        self.timeout = timeout

    @abstractmethod
    def generate(self, system_prompt: str, user_prompt: str) -> str:
        """Send a prompt and return the raw text response.

        Implementations should raise LLMError on any failure so callers can
        degrade gracefully (flakeradar always works without AI analysis).
        """
        raise NotImplementedError
