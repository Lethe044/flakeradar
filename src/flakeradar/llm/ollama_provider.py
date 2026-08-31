from __future__ import annotations

import requests

from .base import LLMError, LLMProvider

_DEFAULT_URL = "http://localhost:11434/api/chat"


class OllamaProvider(LLMProvider):
    """Local inference via Ollama. No API key, no cost, no rate limit."""

    name = "ollama"

    def generate(self, system_prompt: str, user_prompt: str) -> str:
        url = self.base_url or _DEFAULT_URL
        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "stream": False,
            "options": {"temperature": 0.2},
        }
        try:
            resp = requests.post(url, json=payload, timeout=self.timeout)
        except requests.RequestException as exc:
            raise LLMError(
                f"Could not reach Ollama at {url}: {exc}. "
                "Is Ollama running? (https://ollama.com)"
            ) from exc
        if resp.status_code != 200:
            raise LLMError(f"Ollama error {resp.status_code}: {resp.text[:500]}")
        try:
            data = resp.json()
            return data["message"]["content"]
        except (KeyError, ValueError) as exc:
            raise LLMError(f"Unexpected Ollama response shape: {exc}") from exc
