"""Regression tests for subagent runner ownership context."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


@pytest.mark.asyncio
async def test_subagent_skill_describe_receives_owner_id(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from modules.agent.backend.services import subagent_runner

    captured_owner_ids: list[int | None] = []
    call_count = 0

    async def fake_chat(**kwargs: object) -> dict:
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            return {
                "content": "",
                "tool_calls": [{
                    "id": "call_1",
                    "type": "function",
                    "function": {
                        "name": "skill_describe",
                        "arguments": json.dumps({"name": "knowledge__search"}),
                    },
                }],
            }
        return {"content": "done", "tool_calls": []}

    async def fake_handle_skill_describe(
        params: dict,
        role: str,
        owner_id: int | None = None,
        agent_code: str = "default",
    ) -> dict:
        captured_owner_ids.append(owner_id)
        return {"name": params["name"], "agent_code": agent_code}

    monkeypatch.setattr(subagent_runner.gateway_router, "chat", fake_chat)
    monkeypatch.setattr(
        subagent_runner.tool_discovery,
        "handle_skill_describe",
        fake_handle_skill_describe,
    )

    result = await subagent_runner._execute_tool_loop(
        messages=[{"role": "system", "content": "test"}],
        task_tools=[],
        max_rounds=2,
        task_write_enabled=False,
        caller="user:55",
        caller_role="viewer",
        owner_id=55,
        task_desc="describe a skill",
    )

    assert result["status"] == "completed"
    assert result["conclusion"] == "done"
    assert captured_owner_ids == [55]
    assert result["tool_calls"][0]["name"] == "skill_describe"
    assert result["tool_results"][0]["result"]["name"] == "knowledge__search"


@pytest.mark.asyncio
async def test_subagent_write_guard_blocks_skill_use_write_capability(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from modules.agent.backend.services import subagent_runner

    async def fake_chat(**kwargs: object) -> dict:
        return {
            "content": "",
            "tool_calls": [{
                "id": "call_write",
                "type": "function",
                "function": {
                    "name": "skill_use",
                    "arguments": json.dumps({
                        "name": "agent__update_my_profile",
                        "args": {"profile_data": {"tone": "formal"}},
                    }),
                },
            }],
        }

    async def forbidden_handle_skill_use(*args: object, **kwargs: object) -> dict:
        raise AssertionError("write capability should be blocked before skill_use dispatch")

    monkeypatch.setattr(subagent_runner.gateway_router, "chat", fake_chat)
    monkeypatch.setattr(
        subagent_runner.tool_discovery,
        "handle_skill_use",
        forbidden_handle_skill_use,
    )

    result = await subagent_runner._execute_tool_loop(
        messages=[{"role": "system", "content": "test"}],
        task_tools=[],
        max_rounds=1,
        task_write_enabled=False,
        caller="user:55",
        caller_role="viewer",
        owner_id=55,
        task_desc="try to update profile",
    )

    assert result["status"] == "error"
    assert "写入权限" in result["error"]
    assert "agent__update_my_profile" in result["error"]
    assert result["tool_results"][0]["name"] == "skill_use"
    assert "写入权限" in result["tool_results"][0]["result"]["error"]


@pytest.mark.asyncio
async def test_subagent_write_guard_allows_skill_use_read_capability(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from modules.agent.backend.services import subagent_runner

    call_count = 0
    captured_params: list[dict] = []

    async def fake_chat(**kwargs: object) -> dict:
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            return {
                "content": "",
                "tool_calls": [{
                    "id": "call_read",
                    "type": "function",
                    "function": {
                        "name": "skill_use",
                        "arguments": json.dumps({
                            "name": "knowledge__search",
                            "args": {"query": "agent"},
                        }),
                    },
                }],
            }
        return {"content": "read done", "tool_calls": []}

    async def fake_handle_skill_use(params: dict, caller: str, caller_role: str) -> dict:
        captured_params.append(params)
        return {"success": True, "data": {"results": []}}

    monkeypatch.setattr(subagent_runner.gateway_router, "chat", fake_chat)
    monkeypatch.setattr(
        subagent_runner.tool_discovery,
        "handle_skill_use",
        fake_handle_skill_use,
    )

    result = await subagent_runner._execute_tool_loop(
        messages=[{"role": "system", "content": "test"}],
        task_tools=[],
        max_rounds=2,
        task_write_enabled=False,
        caller="user:55",
        caller_role="viewer",
        owner_id=55,
        task_desc="search knowledge",
    )

    assert result["status"] == "completed"
    assert result["conclusion"] == "read done"
    assert captured_params == [{"name": "knowledge__search", "args": {"query": "agent"}}]


@pytest.mark.asyncio
async def test_spawn_subagent_track_trajectory_persists(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app import database

    from modules.agent.backend.handlers import tool as tool_handler
    from modules.agent.backend.services import (
        subagent_runner,
        trajectory_service,
    )

    class DummySession:
        async def __aenter__(self) -> object:
            return object()

        async def __aexit__(self, exc_type: object, exc: object, tb: object) -> None:
            return None

    async def fake_run_single_task(**kwargs: object) -> dict:
        return {
            "task": kwargs["task_desc"],
            "status": "completed",
            "error": None,
            "conclusion": "subagent done",
            "rounds_used": 1,
            "tool_calls": [{"name": "skill_list", "arguments": {}}],
            "tool_results": [{"name": "skill_list", "result": {"skills": []}}],
        }

    captured: dict[str, object] = {}

    async def fake_record_turn(db: object, **kwargs: object) -> dict:
        captured.update(kwargs)
        return {"id": 123, "turn_index": kwargs["turn_index"], "recorded": True}

    monkeypatch.setattr(database, "AsyncSessionLocal", lambda: DummySession())
    monkeypatch.setattr(subagent_runner, "run_single_task", fake_run_single_task)
    monkeypatch.setattr(trajectory_service, "record_turn", fake_record_turn)

    result = await tool_handler._cap_spawn_subagent(
        {
            "task": "inspect data",
            "track_trajectory": True,
            "conversation_id": 777,
            "session_id": "subagent-test",
            "turn_index_offset": 0,
        },
        caller="user:55",
    )

    assert result["completed"] == 1
    assert result["trajectory"][0]["recorded"] is True
    assert result["trajectory"][0]["id"] == 123
    assert captured["conversation_id"] == 777
    assert captured["owner_id"] == 55
    assert captured["session_id"] == "subagent-test"
    assert captured["tool_calls"] == [{"name": "skill_list", "arguments": {}}]
    assert captured["assistant_response"] == "subagent done"
