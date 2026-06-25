"""In-process event system for cross-module decoupling — unified governance control plane.

Governance contract shared with module_registry.py:
  - module_key       : identity
  - contract_version : event handler contract version (semver)
  - timeout          : per-handler timeout in seconds
  - trusted_callers  : caller prefix whitelist (empty = all allowed)
  - side_effect_level: "readonly" | "low" | "medium" | "high"
  - owner            : the module_key declaring this handler
  - trace_id         : cross-capability/event/retry trace chain

Every governance field here mirrors the same-named field in module_registry
so that capability calls and event emissions share one diagnostic language.
"""

import logging
import uuid
from typing import Awaitable, Callable
from datetime import datetime, timezone

logger = logging.getLogger("v2.module_events")

EventHandler = Callable[[dict, str, str], Awaitable[dict]]

_event_handlers: dict[str, list[dict]] = {}
"""event_name -> [{module_key, handler, description, contract_version,
                   timeout, trusted_callers, side_effect_level, owner}]"""

# Side effect levels (same values as module_registry)
SIDE_EFFECT_READONLY = "readonly"
SIDE_EFFECT_LOW = "low"
SIDE_EFFECT_MEDIUM = "medium"
SIDE_EFFECT_HIGH = "high"
_SIDE_EFFECT_ORDER = {SIDE_EFFECT_READONLY: 0, SIDE_EFFECT_LOW: 1, SIDE_EFFECT_MEDIUM: 2, SIDE_EFFECT_HIGH: 3}

SIDE_EFFECT_LEVELS = list(_SIDE_EFFECT_ORDER.keys())


def register_module_event_handler(
    event_name: str,
    handler: EventHandler,
    module_key: str,
    description: str = "",
    contract_version: str = "1.0.0",
    timeout: float | None = None,
    trusted_callers: list[str] | None = None,
    side_effect_level: str = SIDE_EFFECT_MEDIUM,
) -> None:
    """Module registers itself to receive event_name events.

    Governance fields (shared with module_registry.register_capability):
      - description      : 事件处理器的用途说明
      - contract_version : 事件契约版本号
      - timeout          : 处理器执行超时秒数（None = 不限制）
      - trusted_callers  : 允许 emit 该事件的 caller 前缀白名单
      - side_effect_level: 副作用等级
    """
    if side_effect_level not in _SIDE_EFFECT_ORDER:
        raise ValueError(f"Invalid side_effect_level: {side_effect_level}. Must be one of {SIDE_EFFECT_LEVELS}")
    if event_name not in _event_handlers:
        _event_handlers[event_name] = []
    existing = [e for e in _event_handlers[event_name] if e["module_key"] == module_key]
    entry = {
        "module_key": module_key,
        "handler": handler,
        "description": description,
        "contract_version": contract_version,
        "timeout": timeout,
        "trusted_callers": trusted_callers or [],
        "side_effect_level": side_effect_level,
        "owner": module_key,
    }
    if existing:
        existing[0].update(entry)
    else:
        _event_handlers[event_name].append(entry)
    logger.info(
        "Registered event handler: %s <- %s (contract=%s side_effect=%s)",
        event_name, module_key, contract_version, side_effect_level,
    )


async def emit_module_event(
    event_name: str,
    payload: dict,
    caller: str,
    caller_role: str = "viewer",
    trace_id: str | None = None,
) -> list[dict]:
    """Emit an event. Each registered handler is called sequentially.

    trace_id: 调用方传入的追踪 ID，与 call_capability 的 trace 共用同一共识。

    Governance enforcement:
      - trusted_callers: if non-empty, caller must match a prefix in the list
    Returns per-handler results with full governance trace metadata.
    """
    trace_id = trace_id or str(uuid.uuid4())
    handlers = _event_handlers.get(event_name, [])
    if not handlers:
        logger.debug("No handlers registered for event '%s'", event_name)
        return []

    results: list[dict] = []
    for entry in handlers:
        trusted = entry.get("trusted_callers", [])
        if trusted:
            allowed = any(caller.startswith(p) for p in trusted)
            if not allowed:
                logger.warning(
                    "Event '%s' caller='%s' not in trusted_callers=%s for module '%s' — skipping",
                    event_name, caller, trusted, entry["module_key"],
                )
                results.append({
                    "module_key": entry["module_key"],
                    "success": False,
                    "error": "caller not in trusted_callers",
                    "_trace": {
                        "trace_id": trace_id,
                        "event": event_name,
                        "contract_version": entry.get("contract_version", "1.0.0"),
                        "timeout": entry.get("timeout"),
                        "side_effect_level": entry.get("side_effect_level", SIDE_EFFECT_MEDIUM),
                        "owner": entry.get("owner", entry["module_key"]),
                        "ts": datetime.now(timezone.utc).isoformat(),
                    },
                })
                continue
        try:
            handler_result = await entry["handler"](payload, caller, caller_role)
            results.append({
                "module_key": entry["module_key"],
                "success": True,
                "result": handler_result,
                "_trace": {
                    "trace_id": trace_id,
                    "event": event_name,
                    "contract_version": entry.get("contract_version", "1.0.0"),
                    "timeout": entry.get("timeout"),
                    "side_effect_level": entry.get("side_effect_level", SIDE_EFFECT_MEDIUM),
                    "owner": entry.get("owner", entry["module_key"]),
                    "ts": datetime.now(timezone.utc).isoformat(),
                },
            })
        except Exception as exc:
            logger.warning(
                "Event '%s' handler for module '%s' failed: %s",
                event_name, entry["module_key"], exc,
            )
            results.append({
                "module_key": entry["module_key"],
                "success": False,
                "error": str(exc),
                "_trace": {
                    "trace_id": trace_id,
                    "event": event_name,
                    "contract_version": entry.get("contract_version", "1.0.0"),
                    "timeout": entry.get("timeout"),
                    "side_effect_level": entry.get("side_effect_level", SIDE_EFFECT_MEDIUM),
                    "owner": entry.get("owner", entry["module_key"]),
                    "ts": datetime.now(timezone.utc).isoformat(),
                },
            })
    return results
