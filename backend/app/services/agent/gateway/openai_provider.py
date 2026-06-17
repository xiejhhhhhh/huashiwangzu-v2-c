import json
import logging
from typing import AsyncGenerator

import httpx

from .adapters import get_adapter
from .base import BaseProvider
from .stream_parse import error_message, extract_stream_payload, format_error

logger = logging.getLogger("v2.agent.openai_compat")


class OpenAIProvider(BaseProvider):
    def __init__(self, api_url: str, api_key: str = "", provider_name: str = "opencode"):
        self.api_url = api_url
        self.api_key = api_key
        self.provider_name = provider_name

    def _headers(self) -> dict[str, str]:
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        return headers

    async def chat(
        self, messages: list[dict], model: str, temperature: float = 0.7,
        max_tokens: int = 4096, tools: list[dict] | None = None,
    ) -> dict:
        payload = _payload(messages, model, temperature, max_tokens, False, tools)
        async with httpx.AsyncClient(timeout=120) as client:
            resp = await client.post(self.api_url, json=payload, headers=self._headers())
            resp.raise_for_status()
            return resp.json()

    async def chat_stream(
        self, messages: list[dict], model: str, temperature: float = 0.7,
        max_tokens: int = 4096, tools: list[dict] | None = None,
    ) -> AsyncGenerator[dict, None]:
        adapter = get_adapter(model)
        payload = _payload(messages, model, temperature, max_tokens, True, tools)
        try:
            async with httpx.AsyncClient(timeout=300) as client:
                async with client.stream("POST", self.api_url, json=payload, headers=self._headers()) as resp:
                    if resp.status_code >= 400:
                        yield {"type": "error", "content": error_message(resp.status_code, await resp.aread())}
                        return
                    async for line in resp.aiter_lines():
                        chunk = extract_stream_payload(line)
                        if chunk is None:
                            continue
                        if chunk == "[DONE]":
                            yield {"type": "done", "content": ""}
                            return
                        try:
                            data = json.loads(chunk)
                        except json.JSONDecodeError:
                            continue
                        if "error" in data:
                            yield {"type": "error", "content": format_error(data["error"])}
                            return
                        event = adapter.adapt_stream_chunk(data, provider=self.provider_name)
                        if event:
                            yield event
                            if event["type"] == "done":
                                return
        except Exception as e:
            logger.error("OpenAI-compatible stream error: %s", e)
            yield {"type": "error", "content": str(e)}

    async def check_health(self) -> bool:
        try:
            async with httpx.AsyncClient(timeout=5) as client:
                resp = await client.get(self.api_url.replace("/chat/completions", "/models"), headers=self._headers())
                return resp.status_code == 200
        except Exception as e:
            logger.warning("OpenAI-compatible health check failed: %s", e)
            return False


def _payload(
    messages: list[dict], model: str, temperature: float, max_tokens: int,
    stream: bool, tools: list[dict] | None,
) -> dict:
    data = {"model": model, "messages": messages, "temperature": temperature, "max_tokens": max_tokens, "stream": stream}
    if tools:
        data["tools"] = tools
    return data
