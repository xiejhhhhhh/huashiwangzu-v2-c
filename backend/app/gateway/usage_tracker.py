from __future__ import annotations

import logging
from dataclasses import asdict, dataclass
from datetime import date

logger = logging.getLogger("v2.gateway.usage")


@dataclass
class UsageRecord:
    model_key: str
    provider_name: str
    caller_module: str
    prompt_tokens: int = 0
    completion_tokens: int = 0
    duration_ms: float = 0.0
    success: bool = True
    error_category: str = ""


USAGE_LOGGING_ENABLED = True


async def log_usage(
    model_key: str,
    prompt_tokens: int,
    completion_tokens: int,
    provider_name: str = "",
    caller_module: str = "gateway",
    duration_ms: float = 0.0,
    success: bool = True,
    error_category: str = "",
) -> None:
    if not USAGE_LOGGING_ENABLED:
        return
    if prompt_tokens <= 0 and completion_tokens <= 0:
        return
    try:
        from app.gateway.config import MODEL_PROFILES

        profile = MODEL_PROFILES.get(model_key)
        if not profile:
            return
        price_input = profile.get("price_input") or 0
        price_output = profile.get("price_output") or 0
        if not price_input and not price_output:
            return
        cost = (prompt_tokens * price_input + completion_tokens * price_output) / 1_000_000

        from sqlalchemy import text

        from app.database import AsyncSessionLocal

        today = date.today()
        async with AsyncSessionLocal() as db:
            await db.execute(text("""
                INSERT INTO framework_gateway_usage_daily
                (usage_date, model_key, provider, module, call_count,
                 prompt_tokens, completion_tokens, cost)
                VALUES (:date, :model, :provider, :module, 1,
                        :prompt_tokens, :completion_tokens, :cost)
                ON CONFLICT (usage_date, model_key, provider, module)
                DO UPDATE SET
                    call_count = framework_gateway_usage_daily.call_count + 1,
                    prompt_tokens = framework_gateway_usage_daily.prompt_tokens + :prompt_tokens,
                    completion_tokens = framework_gateway_usage_daily.completion_tokens + :completion_tokens,
                    cost = framework_gateway_usage_daily.cost + :cost
            """), {
                "date": today,
                "model": model_key,
                "provider": provider_name,
                "module": caller_module,
                "prompt_tokens": prompt_tokens,
                "completion_tokens": completion_tokens,
                "cost": cost,
            })
            await db.commit()
    except Exception as e:
        logger.warning("Usage logging failed (non-fatal): %s", e)


def format_usage_log(record: UsageRecord) -> str:
    parts = [
        f"model={record.model_key}",
        f"provider={record.provider_name}",
        f"module={record.caller_module}",
        f"prompt={record.prompt_tokens}",
        f"completion={record.completion_tokens}",
        f"duration={record.duration_ms:.0f}ms",
    ]
    if record.error_category:
        parts.append(f"error={record.error_category}")
    return " | ".join(parts)


def log_usage_event(record: UsageRecord) -> None:
    level = logger.info if record.success else logger.warning
    level("[USAGE] %s", format_usage_log(record))
    logger.debug("[USAGE_RAW] %s", asdict(record))
