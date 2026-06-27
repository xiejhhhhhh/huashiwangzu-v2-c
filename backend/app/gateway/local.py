import asyncio
from typing import AsyncGenerator
from .base import BaseProvider


class LocalProvider(BaseProvider):
    async def chat(
        self,
        messages: list[dict],
        model: str,
        temperature: float = 0.7,
        max_tokens: int = 4096,
        tools: list[dict] | None = None,
    ) -> dict:
        last = messages[-1]["content"] if messages else ""
        return {"content": f"[Local echo] {last[:64]}", "thinking": ""}

    async def chat_stream(
        self,
        messages: list[dict],
        model: str,
        temperature: float = 0.7,
        max_tokens: int = 4096,
        tools: list[dict] | None = None,
    ) -> AsyncGenerator[dict, None]:
        last = messages[-1]["content"] if messages else ""
        words = f"[Local echo] {last[:64]}".split(" ")
        for word in words:
            await asyncio.sleep(0.05)
            yield {"type": "token", "content": word + " "}
        yield {"type": "done", "content": ""}

    async def check_health(self) -> bool:
        return True
