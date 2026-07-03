"""Agent task handler registration tests."""

import importlib

from app.services import task_worker

from modules.agent.backend import bootstrap
from modules.agent.backend.handlers import tasks
from modules.agent.backend.services.profile_evolve import handle_profile_evolve

AGENT_TASK_TYPES = [
    "profile_evolve",
    "memory_dream",
    "memory_distill",
    "agent_execute_slow_tool",
    "workflow_mine",
    "agent_context_compact",
]


def test_register_agent_tasks_keeps_profile_evolve_registered() -> None:
    """Bootstrap is the single source for agent task handler registration."""
    original_handlers = dict(task_worker._HANDLERS)

    try:
        for task_type in AGENT_TASK_TYPES:
            task_worker._HANDLERS.pop(task_type, None)

        reloaded_tasks = importlib.reload(tasks)
        for task_type in AGENT_TASK_TYPES:
            assert task_type not in task_worker._HANDLERS

        bootstrap.register_agent_tasks()

        expected_handlers = {
            "profile_evolve": handle_profile_evolve,
            "memory_dream": reloaded_tasks._handle_memory_dream,
            "memory_distill": reloaded_tasks._handle_memory_distill,
            "agent_execute_slow_tool": reloaded_tasks._handle_slow_tool,
            "workflow_mine": reloaded_tasks._handle_workflow_mine,
            "agent_context_compact": reloaded_tasks._handle_context_compact,
        }
        for task_type, handler in expected_handlers.items():
            assert task_worker._HANDLERS[task_type] is handler
    finally:
        task_worker._HANDLERS.clear()
        task_worker._HANDLERS.update(original_handlers)


def test_importing_agent_router_registers_worker_handlers() -> None:
    """Manifest loading imports router.py, so router import must bootstrap worker handlers."""
    original_handlers = dict(task_worker._HANDLERS)

    try:
        for task_type in AGENT_TASK_TYPES:
            task_worker._HANDLERS.pop(task_type, None)

        router_module = importlib.import_module("modules.agent.backend.router")
        importlib.reload(router_module)

        for task_type in AGENT_TASK_TYPES:
            assert task_type in task_worker._HANDLERS
    finally:
        task_worker._HANDLERS.clear()
        task_worker._HANDLERS.update(original_handlers)
