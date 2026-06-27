"""Lightweight in-process event system (backward-compatible wrapper).

Delegates registration and emission to the persistent event_bus module.
Maintains the same API for existing consumers (knowledge router, file_transfer).
"""

from app.services.event_bus import (
    register_module_event_handler,
    emit_module_event,
    get_event_log,
    retry_failed_events,
    replay_event,
)

__all__ = [
    "register_module_event_handler",
    "emit_module_event",
    "get_event_log",
    "retry_failed_events",
    "replay_event",
]
