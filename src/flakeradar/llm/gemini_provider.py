from __future__ import annotations

import requests

from .base import LLMError, LLMProvider

_DEFAULT_URL_TEMPLATE = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"


class GeminiProvider(LLMProvider):
    """Google Gemini API (has a free tier for lightweight models)."""

    name = "gemini"

    def generate(self, system_prompt: str, user_prompt: str) -> str:
        if not self.api_key:
            raise LLMError("Gemini provider requires an API key (FLAKERADAR_LLM_API_KEY or GEMINI_API_KEY)")
        url = self.base_url or _DEFAULT_URL_TEMPLATE.format(model=self.model)
        payload = {
            "system_instruction": {"parts": [{"text": system_prompt}]},
            "contents": [{"role": "user", "parts": [{"text": user_prompt}]}],
            "generationConfig": {"temperature": 0.2, "maxOutputTokens": 800},
        }
        headers = {"Content-Type": "application/json", "x-goog-api-key": self.api_key}
        try:
            resp = requests.post(url, json=payload, headers=headers, timeout=self.timeout)
        except requests.RequestException as exc:
            raise LLMError(f"Gemini request failed: {exc}") from exc
        if resp.status_code != 200:
            raise LLMError(f"Gemini API error {resp.status_code}: {resp.text[:500]}")
        try:
            data = resp.json()
            parts = data["candidates"][0]["content"]["parts"]
            return "".join(p.get("text", "") for p in parts)
        except (KeyError, IndexError, ValueError) as exc:
            raise LLMError(f"Unexpected Gemini response shape: {exc}") from exc
