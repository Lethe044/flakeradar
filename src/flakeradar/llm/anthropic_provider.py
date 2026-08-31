from __future__ import annotations

import requests

from .base import LLMError, LLMProvider

_DEFAULT_URL = "https://api.anthropic.com/v1/messages"
_ANTHROPIC_VERSION = "2023-06-01"


class AnthropicProvider(LLMProvider):
    """Anthropic Messages API. Optional - requires the user's own key."""

    name = "anthropic"

    def generate(self, system_prompt: str, user_prompt: str) -> str:
        if not self.api_key:
            raise LLMError("Anthropic provider requires an API key (FLAKERADAR_LLM_API_KEY or ANTHROPIC_API_KEY)")
        url = self.base_url or _DEFAULT_URL
        payload = {
            "model": self.model,
            "max_tokens": 800,
            "system": system_prompt,
            "messages": [{"role": "user", "content": user_prompt}],
        }
        headers = {
            "x-api-key": self.api_key,
            "anthropic-version": _ANTHROPIC_VERSION,
            "Content-Type": "application/json",
        }
        try:
            resp = requests.post(url, json=payload, headers=headers, timeout=self.timeout)
        except requests.RequestException as exc:
            raise LLMError(f"Anthropic request failed: {exc}") from exc
        if resp.status_code != 200:
            raise LLMError(f"Anthropic API error {resp.status_code}: {resp.text[:500]}")
        try:
            data = resp.json()
            return "".join(block.get("text", "") for block in data.get("content", []))
        except (KeyError, ValueError) as exc:
            raise LLMError(f"Unexpected Anthropic response shape: {exc}") from exc
