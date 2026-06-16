from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.knowledge import LlmLog


async def log_llm_call(
    db: AsyncSession,
    caller: str,
    model: str,
    system_prompt: str | None,
    user_input: str | None,
    raw_response: str | None,
    parse_ok: bool,
    result: dict | None,
    error: str | None,
    duration_ms: int,
    cost: float = 0.0,
) -> None:
    log = LlmLog(
        caller=caller,
        model=model,
        system_prompt=system_prompt,
        user_input=user_input,
        raw_response=raw_response,
        parse_ok=parse_ok,
        result=result,
        error=error,
        duration_ms=duration_ms,
        cost=cost,
    )
    db.add(log)
    await db.commit()
