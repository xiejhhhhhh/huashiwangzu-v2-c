import uuid
from sqlalchemy.ext.asyncio import AsyncSession
from app.models.system import SystemLog

LOG_LEVELS = {
    "DEBUG": "debug", "INFO": "info", "WARNING": "warning",
    "ERROR": "error", "CRITICAL": "critical",
}

CATEGORIES = {
    "GENERAL": "general", "AUTH": "auth", "DESKTOP": "desktop",
    "BACKGROUND_TASK": "background_task",
    "SYSTEM_CONFIG": "system_config", "NOTIFICATION": "notification",
    "PERMISSION": "permission", "EXCEPTION": "exception",
}

_trace_id: str | None = None


def get_trace_id() -> str:
    global _trace_id
    if _trace_id is None:
        _trace_id = str(uuid.uuid4())
    return _trace_id


def reset_trace_id():
    global _trace_id
    _trace_id = None


SENSITIVE_KEYS = {"password", "token", "secret", "authorization", "密钥", "密码", "令牌"}


def _sanitize(data: dict) -> dict:
    cleaned = {}
    for k, v in data.items():
        if any(s in k.lower() for s in SENSITIVE_KEYS):
            cleaned[k] = "[REDACTED]"
        elif isinstance(v, str) and len(v) > 500:
            cleaned[k] = v[:200] + "..."
        elif isinstance(v, dict):
            cleaned[k] = _sanitize(v)
        else:
            cleaned[k] = v
    return cleaned


async def write_log(
    db: AsyncSession,
    level: str,
    module: str,
    action: str,
    message: str,
    user_id: int = 0,
    ip: str = "",
    data: dict | None = None,
    duration_ms: int = 0,
) -> None:
    safe_data = _sanitize(data or {})
    safe_data["trace_id"] = get_trace_id()
    log = SystemLog(
        level=level, module=module, action=action,
        message=message[:500] if message else "",
        user_id=user_id or 0, ip_address=ip,
        request_data=safe_data if safe_data else None,
        duration_ms=duration_ms,
    )
    db.add(log)
    await db.commit()


async def write_structured_log(
    db: AsyncSession,
    level: str,
    category: str,
    message: str,
    task_id: int | None = None,
    file_id: int | None = None,
    phase: str | None = None,
    duration_ms: int | None = None,
    error_type: str | None = None,
    extra_data: dict | None = None,
    user_id: int = 0,
) -> None:
    ctx = {}
    if task_id is not None:
        ctx["task_id"] = task_id
    if file_id is not None:
        ctx["file_id"] = file_id
    if phase is not None:
        ctx["phase"] = phase
    if duration_ms is not None:
        ctx["duration_ms"] = duration_ms
    if error_type is not None:
        ctx["error_type"] = error_type
    if extra_data:
        ctx.update(extra_data)
    await write_log(db, level, category, message, user_id=user_id, data=ctx)
