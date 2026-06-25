import asyncio
import json
import logging
from typing import AsyncGenerator

import httpx

from .adapters import get_adapter
from .base import BaseProvider
from .stream_parse import error_message, extract_stream_payload, format_error

logger = logging.getLogger("v2.gateway.openai_compat")

_DEFAULT_TIMEOUT = {"connect": 10, "read": 120, "write": 30, "stream_chunk": 60}


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

    def _resolve_timeout(self, timeout: dict | None) -> tuple[httpx.Timeout, float]:
        t = timeout or _DEFAULT_TIMEOUT
        connect = t.get("connect", _DEFAULT_TIMEOUT["connect"])
        read = t.get("read", _DEFAULT_TIMEOUT["read"])
        write = t.get("write", _DEFAULT_TIMEOUT["write"])
        stream_chunk = t.get("stream_chunk", _DEFAULT_TIMEOUT["stream_chunk"])
        # pool 必须是具体值: 不给 default 时 httpx.Timeout 要求四个参数全部非 None
        pool = t.get("pool", connect)
        return httpx.Timeout(connect=connect, read=read, write=write, pool=pool), stream_chunk

    async def chat(
        self, messages: list[dict], model: str, temperature: float = 0.7,
        max_tokens: int = 4096, tools: list[dict] | None = None,
        timeout: dict | None = None,
    ) -> dict:
        payload = _payload(messages, model, temperature, max_tokens, False, tools)
        httpx_timeout, _ = self._resolve_timeout(timeout)
        async with httpx.AsyncClient(timeout=httpx_timeout) as client:
            resp = await client.post(self.api_url, json=payload, headers=self._headers())
            if resp.status_code >= 400:
                body_text = await _read_error_body(resp)
                payload_preview = json.dumps(payload, ensure_ascii=False)[:2000]
                logger.error(
                    "AI provider %s returned %s\n请求体: %s\n响应体: %s",
                    self.provider_name, resp.status_code, payload_preview, body_text,
                )
                resp.raise_for_status()
            return resp.json()

    async def chat_stream(
        self, messages: list[dict], model: str, temperature: float = 0.7,
        max_tokens: int = 4096, tools: list[dict] | None = None,
        timeout: dict | None = None,
    ) -> AsyncGenerator[dict, None]:
        adapter = get_adapter(model)
        payload = _payload(messages, model, temperature, max_tokens, True, tools)
        httpx_timeout, stream_chunk_timeout = self._resolve_timeout(timeout)
        try:
            async with httpx.AsyncClient(timeout=httpx_timeout) as client:
                async with client.stream("POST", self.api_url, json=payload, headers=self._headers()) as resp:
                    if resp.status_code >= 400:
                        yield {"type": "error", "content": error_message(resp.status_code, await resp.aread())}
                        return
                    async for line in _iter_lines_with_timeout(resp, stream_chunk_timeout):
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
        except asyncio.TimeoutError:
            logger.error("OpenAI-compatible stream timed out (no chunk for %.1fs)", stream_chunk_timeout)
            yield {"type": "error", "content": "Stream timed out — no response chunk received"}
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


async def _iter_lines_with_timeout(
    resp: httpx.Response,
    chunk_timeout: float,
) -> AsyncGenerator[str, None]:
    it = resp.aiter_lines()
    while True:
        try:
            line = await asyncio.wait_for(
                it.__anext__(),
                timeout=chunk_timeout,
            )
        except StopAsyncIteration:
            break
        except asyncio.TimeoutError:
            raise asyncio.TimeoutError(f"No stream chunk received within {chunk_timeout}s")
        yield line


async def _read_error_body(resp: httpx.Response) -> str:
    try:
        body = resp.text
        return body[:500] if len(body) > 500 else body
    except Exception:
        return "(无法读取响应体)"


def _payload(
    messages: list[dict], model: str, temperature: float, max_tokens: int,
    stream: bool, tools: list[dict] | None,
) -> dict:
    data = {"model": model, "messages": messages, "temperature": temperature, "max_tokens": max_tokens, "stream": stream}
    if tools:
        data["tools"] = tools
    return data
