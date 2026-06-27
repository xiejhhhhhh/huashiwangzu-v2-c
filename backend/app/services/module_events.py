"""Lightweight in-process event system for cross-module decoupling.

Replaces hardcoded call_capability in framework code with event emission.
Module handlers register interest in events; framework code emits events
without knowing which modules (if any) will handle them.

Handler signature: async def(payload: dict, caller: str, caller_role: str) -> dict
Single handler failure is logged but does not block other handlers.
"""

import logging

from typing import Awaitable, Callable

logger = logging.getLogger("v2.module_events")

EventHandler = Callable[[dict, str, str], Awaitable[dict]]

_event_handlers: dict[str, list[dict]] = {}
"""event_name -> [{module_key, handler}]"""


def register_module_event_handler(
    event_name: str,
    handler: EventHandler,
    module_key: str,
) -> None:
    """Module registers itself to receive event_name events.

    The same module may register at most one handler per event (duplicate
    registration is idempotent — the last registration wins for that module).
    """
    if event_name not in _event_handlers:
        _event_handlers[event_name] = []
    existing = [e for e in _event_handlers[event_name] if e["module_key"] == module_key]
    if existing:
        existing[0]["handler"] = handler
    else:
        _event_handlers[event_name].append({
            "module_key": module_key,
            "handler": handler,
        })


async def emit_module_event(
    event_name: str,
    payload: dict,
    caller: str,
    caller_role: str = "viewer",
) -> list[dict]:
    """Emit an event. Each registered handler is called sequentially.

    Returns a list of per-handler results: {module_key, success, result|error}.
    A single handler failure does not prevent other handlers from running.
    """
    handlers = _event_handlers.get(event_name, [])
    if not handlers:
        logger.debug("No handlers registered for event '%s'", event_name)
        return []

    results: list[dict] = []
    for entry in handlers:
        try:
            handler_result = await entry["handler"](payload, caller, caller_role)
            results.append({
                "module_key": entry["module_key"],
                "success": True,
                "result": handler_result,
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
            })
    return results
