from __future__ import annotations

import requests

from .base import LLMError, LLMProvider

_DEFAULT_URL = "https://api.openai.com/v1/chat/completions"


class OpenAIProvider(LLMProvider):
    """OpenAI chat completions. Optional - requires the user's own key."""

    name = "openai"

    def generate(self, system_prompt: str, user_prompt: str) -> str:
        if not self.api_key:
            raise LLMError("OpenAI provider requires an API key (FLAKERADAR_LLM_API_KEY or OPENAI_API_KEY)")
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
            raise LLMError(f"OpenAI request failed: {exc}") from exc
        if resp.status_code != 200:
            raise LLMError(f"OpenAI API error {resp.status_code}: {resp.text[:500]}")
        try:
            data = resp.json()
            return data["choices"][0]["message"]["content"]
        except (KeyError, IndexError, ValueError) as exc:
            raise LLMError(f"Unexpected OpenAI response shape: {exc}") from exc
