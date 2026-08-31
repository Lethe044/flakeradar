from __future__ import annotations

import requests

from .base import LLMError, LLMProvider

_DEFAULT_URL = "https://api.groq.com/openai/v1/chat/completions"


class GroqProvider(LLMProvider):
    """Groq's OpenAI-compatible chat completions endpoint (generous free tier)."""

    name = "groq"

    def generate(self, system_prompt: str, user_prompt: str) -> str:
        if not self.api_key:
            raise LLMError("Groq provider requires an API key (FLAKERADAR_LLM_API_KEY or GROQ_API_KEY)")
        url = self.base_url or _DEFAULT_URL
        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "temperature": 0.2,
            "max_tokens": 800,
        }
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        try:
            resp = requests.post(url, json=payload, headers=headers, timeout=self.timeout)
        except requests.RequestException as exc:
            raise LLMError(f"Groq request failed: {exc}") from exc
        if resp.status_code != 200:
            raise LLMError(f"Groq API error {resp.status_code}: {resp.text[:500]}")
        try:
            data = resp.json()
            return data["choices"][0]["message"]["content"]
        except (KeyError, IndexError, ValueError) as exc:
            raise LLMError(f"Unexpected Groq response shape: {exc}") from exc
