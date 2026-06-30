from __future__ import annotations

import json
import logging
from typing import AsyncGenerator

import httpx

from app.config import get_settings

from .adapters import get_adapter
from .base import BaseProvider
from .contract import StreamEvent, StreamEventType, stream_event_to_dict
from .protocol import normalize_openai_payload
from .stream_parse import error_message, extract_stream_payload, format_error
from .tool_call_accumulator import StreamingToolCallAccumulator

logger = logging.getLogger("v2.gateway.openai_compat")

OPENCODE_API_URL = "https://opencode.ai/zen/go/v1/chat/completions"


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

    def _build_payload(
        self, messages: list[dict], model: str, temperature: float,
        max_tokens: int, stream: bool, tools: list[dict] | None,
    ) -> dict:
        normalized_messages, normalized_tools = normalize_openai_payload(messages, tools)
        data = {
            "model": model,
            "messages": normalized_messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
            "stream": stream,
        }
        if normalized_tools:
            data["tools"] = normalized_tools
        return data

    async def chat(
        self, messages: list[dict], model: str, temperature: float = 0.7,
        max_tokens: int = 4096, tools: list[dict] | None = None,
    ) -> dict:
        payload = self._build_payload(messages, model, temperature, max_tokens, False, tools)
        async with httpx.AsyncClient(timeout=120, trust_env=False) as client:
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
    ) -> AsyncGenerator[dict, None]:
        adapter = get_adapter(model)
        accumulator = StreamingToolCallAccumulator()
        payload = self._build_payload(messages, model, temperature, max_tokens, True, tools)
        try:
            async with httpx.AsyncClient(timeout=300, trust_env=False) as client:
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
                        choices = data.get("choices") or []
                        choice = choices[0] if choices else {}
                        delta = choice.get("delta") or {}
                        accumulator.add_delta_tool_calls(delta.get("tool_calls"))

                        # 在 finish_reason / [DONE] 之前提取 usage，确保即使 tool_call
                        # 导致下游提前 return，token 计数也不会丢失
                        _usage_raw = data.get("usage")
                        if _usage_raw:
                            yield {"type": "usage", "usage": _usage_raw}

                        if choice.get("finish_reason") == "tool_calls" and accumulator.has_calls():
                            yield stream_event_to_dict(
                                StreamEvent(
                                    type=StreamEventType.TOOL_CALL,
                                    tool_calls=accumulator.completed_tool_calls(),
                                )
                            )
                            continue
                        event = adapter.adapt_stream_chunk(data, provider=self.provider_name)
                        if event:
                            yield stream_event_to_dict(event)
                            if event.type == StreamEventType.DONE:
                                return
        except Exception as e:
            logger.error("OpenAI-compatible stream error: %s", e)
            yield {"type": "error", "content": str(e)}

    async def check_health(self) -> bool:
        try:
            async with httpx.AsyncClient(timeout=5, trust_env=False) as client:
                resp = await client.get(self.api_url.replace("/chat/completions", "/models"), headers=self._headers())
                return resp.status_code == 200
        except Exception as e:
            logger.warning("OpenAI-compatible health check failed: %s", e)
            return False


async def _read_error_body(resp: httpx.Response) -> str:
    try:
        body = resp.text
        return body[:500] if len(body) > 500 else body
    except Exception:
        return "(无法读取响应体)"


class OpenCodeProvider(OpenAIProvider):
    def __init__(self, api_url: str = "", api_key: str = ""):
        super().__init__(
            api_url=api_url or OPENCODE_API_URL,
            api_key=api_key or get_settings().DEEPSEEK_API_KEY,
            provider_name="opencode",
        )
