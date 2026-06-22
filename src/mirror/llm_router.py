from __future__ import annotations

import asyncio
import os
from dataclasses import dataclass
from typing import Any

import httpx

from .settings import MirrorSettings, SpecialistModel


@dataclass(frozen=True)
class LLMResponse:
    text: str
    provider: str
    model: str


class LLMRouter:
    def __init__(self, settings: MirrorSettings) -> None:
        self.settings = settings
        self._semaphore = asyncio.Semaphore(settings.concurrency.max_global_llm_calls)

    async def complete(self, specialist: str, system: str, user: str, *, max_tokens: int = 1200) -> LLMResponse:
        model = self.settings.llm.specialist(specialist)
        async with self._semaphore:
            if model.provider == "ollama":
                return await self._ollama_complete(model, system, user)
            return await self._claude_complete(model, system, user, max_tokens=max_tokens)

    async def _claude_complete(self, model: SpecialistModel, system: str, user: str, *, max_tokens: int) -> LLMResponse:
        api_key = os.environ.get(self.settings.llm.claude_api_key_env)
        if not api_key:
            raise RuntimeError(f"{self.settings.llm.claude_api_key_env} is not set")
        from anthropic import AsyncAnthropic  # type: ignore

        client = AsyncAnthropic(api_key=api_key)
        message = await client.messages.create(
            model=model.model,
            system=system,
            max_tokens=max_tokens,
            messages=[{"role": "user", "content": user}],
        )
        text = "\n".join(block.text for block in message.content if getattr(block, "type", None) == "text")
        return LLMResponse(text=text, provider="claude", model=model.model)

    async def _ollama_complete(self, model: SpecialistModel, system: str, user: str) -> LLMResponse:
        payload: dict[str, Any] = {
            "model": model.model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "stream": False,
        }
        async with httpx.AsyncClient(timeout=120) as client:
            response = await client.post(f"{self.settings.llm.ollama_base_url.rstrip('/')}/api/chat", json=payload)
            response.raise_for_status()
            data = response.json()
        return LLMResponse(text=data.get("message", {}).get("content", ""), provider="ollama", model=model.model)
