"""Sarvam chat completions (OpenAI-compatible): chat(system, user) -> parsed JSON."""
import json
import re

import httpx

from app.clients._http import post_json
from app.config import settings

_FENCE = re.compile(r"^```(?:json)?\s*|\s*```$", re.M)


class LLMJSONError(ValueError):
    pass


def parse_json_object(content: str) -> dict:
    s = _FENCE.sub("", content.strip()).strip()
    try:
        return json.loads(s)
    except json.JSONDecodeError:
        start, end = s.find("{"), s.rfind("}")
        if start >= 0 and end > start:
            try:
                return json.loads(s[start:end + 1])
            except json.JSONDecodeError:
                pass
    raise LLMJSONError(f"Model did not return valid JSON: {content[:300]!r}")


class SarvamLLM:
    def __init__(self, http: httpx.AsyncClient):
        self.http = http

    async def chat(self, system: str, user: str, max_tokens: int | None = None) -> tuple[str, int]:
        body = {
            "model": settings.sarvam_llm_model,
            "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
            "temperature": settings.sarvam_llm_temperature,
            "max_tokens": max_tokens or settings.sarvam_llm_max_tokens,
            "reasoning_effort": settings.sarvam_llm_reasoning_effort,
            "response_format": {"type": "json_object"},
        }
        data = await post_json(self.http, settings.sarvam_llm_path, body)
        content = data["choices"][0]["message"].get("content") or ""
        tokens = int((data.get("usage") or {}).get("total_tokens") or 0)
        return content, tokens

    async def chat_json(self, system: str, user: str, max_tokens: int | None = None) -> tuple[dict, int]:
        content, tokens = await self.chat(system, user, max_tokens)
        return parse_json_object(content), tokens
