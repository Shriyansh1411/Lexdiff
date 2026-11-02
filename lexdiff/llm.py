"""LLM access: any OpenAI-compatible chat-completions endpoint, temperature 0, JSON out.

Configure with environment variables::

    LEXDIFF_LLM_PROVIDER   offline | openai      (default: openai if an API key is set, else offline)
    LEXDIFF_LLM_API_KEY    API key
    LEXDIFF_LLM_BASE_URL   default https://api.openai.com/v1  (any compatible server works)
    LEXDIFF_LLM_MODEL      model name

In *offline* mode no model is called and the deterministic rule-based drafter is used,
so the whole pipeline (and the test-suite) runs with no key and no network.
"""
from __future__ import annotations

import json
import os
import re


class LLMError(RuntimeError):
    pass


class LLMClient:
    def __init__(self, provider=None, model=None, base_url=None, api_key=None, transport=None):
        self.api_key = api_key or os.environ.get("LEXDIFF_LLM_API_KEY", "")
        self.provider = provider or os.environ.get("LEXDIFF_LLM_PROVIDER") or ("openai" if self.api_key else "offline")
        self.model = model or os.environ.get("LEXDIFF_LLM_MODEL", "gpt-4o-mini")
        self.base_url = (base_url or os.environ.get("LEXDIFF_LLM_BASE_URL", "https://api.openai.com/v1")).rstrip("/")
        self.transport = transport  # callable(payload: dict) -> str; used by tests

    @property
    def online(self) -> bool:
        return self.provider != "offline"

    def _post(self, payload: dict) -> str:
        if self.transport is not None:
            return self.transport(payload)
        import requests

        resp = requests.post(
            f"{self.base_url}/chat/completions",
            headers={"Authorization": f"Bearer {self.api_key}"},
            json=payload,
            timeout=60,
        )
        if resp.status_code != 200:
            raise LLMError(f"LLM HTTP {resp.status_code}: {resp.text[:300]}")
        return resp.json()["choices"][0]["message"]["content"]

    def complete_json(self, system: str, user: str) -> dict:
        if not self.online:
            raise LLMError("offline provider: no model call is made")
        payload = {
            "model": self.model,
            "temperature": 0,
            "response_format": {"type": "json_object"},
            "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
        }
        raw = self._post(payload)
        raw = re.sub(r"^```(?:json)?\s*|\s*```$", "", raw.strip())
        try:
            data = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise LLMError(f"model did not return valid JSON: {exc}") from exc
        if not isinstance(data, dict):
            raise LLMError("model JSON must be an object")
        return data
