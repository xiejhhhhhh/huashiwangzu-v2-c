"""Regression tests for Agent tool failure normalization."""

import json
from collections.abc import AsyncIterator

import pytest

from .runtime import tool_loop_runtime
from .runtime.runtime_policy import RuntimePolicy
from .runtime.stream_emitter import StreamEmitter
from .runtime.tool_failure_normalizer import (
    effective_tool_name,
    normalize_tool_result_for_model,
)
from .runtime.tool_loop_runtime import ToolLoopRuntime


def test_normalize_external_success_false_as_hard_failure() -> None:
    result, signal = normalize_tool_result_for_model(
        {"success": False, "error": "Connection refused"},
        "web-tools__fetch",
    )

    assert isinstance(result, dict)
    assert result["success"] is False
    assert result["error_class"] == "network_error"
    assert result["failure_kind"] == "hard"
    assert result["hard_failure"] is True
    assert result["tool_failure"]["tool_name"] == "web-tools__fetch"
    assert "Do not treat it as successful" in result["model_instruction"]
    assert signal == result["tool_failure"]


def test_normalize_nested_timeout_preserves_transport_success() -> None:
    result, signal = normalize_tool_result_for_model(
        {
            "success": True,
            "data": {
                "success": False,
                "error": "timed out while opening page",
            },
        },
        "browser-tools__open",
    )

    assert isinstance(result, dict)
    assert result["success"] is False
    assert result["transport_success"] is True
    assert result["error"] == "timed out while opening page"
    assert result["error_class"] == "timeout"
    assert result["hard_failure"] is True
    assert signal is not None
    assert signal["source"] == "data"


def test_effective_tool_name_uses_skill_target() -> None:
    assert effective_tool_name(
        {"name": "skill_use", "args": {"name": "web-tools__fetch"}},
    ) == "web-tools__fetch"
    assert effective_tool_name({"name": "skill_list", "args": {}}) == "skill_list"


class _DummySession:
    async def __aenter__(self) -> "_DummySession":
        return self

    async def __aexit__(self, exc_type: object, exc: object, tb: object) -> None:
        return None

    async def execute(self, *args: object, **kwargs: object) -> None:
        raise RuntimeError("skip database in unit test")


class _FakeSink:
    workflow_link = None
    workflow_run_id = None
    workflow_step_id = None

    async def record_failure(self, *args: object, **kwargs: object) -> None:
        return None

    async def persist_assistant(self, *args: object, **kwargs: object) -> int:
        return 123

    async def persist_pending_events(
        self,
        db: object,
        pending_events: list[dict],
        persisted_event_count: int,
    ) -> int:
        return len(pending_events)

    async def generate_completion_evidence(
        self,
        tool_events: list[dict],
        tool_results: list[dict],
    ) -> list[dict]:
        return []

    def check_tool_success(self, tool_events: list[dict]) -> bool:
        return False

    async def record_trajectory(self, *args: object, **kwargs: object) -> dict:
        return {"recorded": False}

    async def run_post_turn_hooks(self, *args: object, **kwargs: object) -> None:
        return None

    async def record_assets(self, *args: object, **kwargs: object) -> list[int]:
        return []


class _FakeOrchestrator:
    async def execute_batch(self, tools: list[dict], execute_fn: object) -> list[dict]:
        return [
            {
                "name": "skill_use",
                "tool_call_id": "call_1",
                "result": {"success": False, "error": "Connection refused"},
            },
        ]


class _ExecutingOrchestrator:
    async def execute_batch(self, tools: list[dict], execute_fn: object) -> list[dict]:
        results = []
        for tool in tools:
            result = await execute_fn(tool)
            results.append({
                "name": tool.get("name", ""),
                "tool_call_id": tool.get("tool_call_id", ""),
                "result": result,
            })
        return results


def _decode_sse_event(event: object) -> dict | None:
    if not isinstance(event, bytes):
        return None
    text = event.decode("utf-8")
    if not text.startswith("data: "):
        return None
    payload = text[6:].strip()
    if payload == "[DONE]":
        return None
    return json.loads(payload)


@pytest.mark.asyncio
async def test_run_marks_external_tool_failure_events(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def fake_stream_until_tool_or_done(
        self: ToolLoopRuntime,
        messages: list[dict],
        tools: list[dict] | None,
        full: list[str],
        thinking_parts: list[str],
        timeline: list[dict],
        emitter: StreamEmitter,
    ) -> AsyncIterator[object]:
        yield {
            "type": "_stream_result",
            "result": {
                "content": "",
                "tool_calls": [
                    {
                        "id": "call_1",
                        "type": "function",
                        "function": {
                            "name": "skill_use",
                            "arguments": {
                                "name": "web-tools__fetch",
                                "args": {"url": "https://example.invalid"},
                            },
                        },
                    },
                ],
                "usage": {},
            },
        }

    async def fake_generate_final_summary(
        self: ToolLoopRuntime,
        messages: list[dict],
        tool_events: list[dict],
        timeline: list[dict],
        full: list[str],
    ) -> AsyncIterator[object]:
        if False:
            yield None

    monkeypatch.setattr(
        ToolLoopRuntime,
        "_stream_until_tool_or_done",
        fake_stream_until_tool_or_done,
    )
    monkeypatch.setattr(
        ToolLoopRuntime,
        "_generate_final_summary",
        fake_generate_final_summary,
    )
    monkeypatch.setattr(tool_loop_runtime, "AsyncSessionLocal", lambda: _DummySession())
    monkeypatch.setattr(tool_loop_runtime, "get_orchestrator", lambda: _FakeOrchestrator())

    runtime = ToolLoopRuntime(
        conversation_id=1,
        owner_id=1,
        policy=RuntimePolicy(max_tool_rounds=1, enable_single_pass_streaming_tools=True),
    )
    messages = [{"role": "user", "content": "fetch a page"}]
    events: list[object] = []

    async for event in runtime.run(
        messages,
        [{"type": "function", "function": {"name": "skill_use"}}],
        _FakeSink(),  # type: ignore[arg-type]
    ):
        events.append(event)

    decoded_events = [_decode_sse_event(event) for event in events]
    assert any(
        event
        and event.get("type") == "tool_result"
        and event.get("hard_failure") is True
        and event.get("error_class") == "network_error"
        for event in decoded_events
    )
    tool_messages = [message for message in messages if message.get("role") == "tool"]
    assert tool_messages
    assert '"success": false' in tool_messages[0]["content"]
    assert '"failure_kind": "hard"' in tool_messages[0]["content"]


@pytest.mark.asyncio
async def test_fast_tool_batch_emits_heartbeat_and_timeout(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def fake_stream_until_tool_or_done(
        self: ToolLoopRuntime,
        messages: list[dict],
        tools: list[dict] | None,
        full: list[str],
        thinking_parts: list[str],
        timeline: list[dict],
        emitter: StreamEmitter,
    ) -> AsyncIterator[object]:
        yield {
            "type": "_stream_result",
            "result": {
                "content": "",
                "tool_calls": [
                    {
                        "id": "call_1",
                        "type": "function",
                        "function": {
                            "name": "skill_list",
                            "arguments": {},
                        },
                    },
                ],
                "usage": {},
            },
        }

    async def fake_generate_final_summary(
        self: ToolLoopRuntime,
        messages: list[dict],
        tool_events: list[dict],
        timeline: list[dict],
        full: list[str],
    ) -> AsyncIterator[object]:
        if False:
            yield None

    async def fake_check_action_allowed(*args: object, **kwargs: object) -> dict:
        return {"allowed": True}

    async def slow_skill_list(*args: object, **kwargs: object) -> dict:
        await tool_loop_runtime.asyncio.sleep(0.05)
        return {"skills": []}

    monkeypatch.setattr(
        ToolLoopRuntime,
        "_stream_until_tool_or_done",
        fake_stream_until_tool_or_done,
    )
    monkeypatch.setattr(
        ToolLoopRuntime,
        "_generate_final_summary",
        fake_generate_final_summary,
    )
    monkeypatch.setattr(tool_loop_runtime, "AsyncSessionLocal", lambda: _DummySession())
    monkeypatch.setattr(tool_loop_runtime, "get_orchestrator", lambda: _ExecutingOrchestrator())
    monkeypatch.setattr(tool_loop_runtime, "check_action_allowed", fake_check_action_allowed)
    monkeypatch.setattr(tool_loop_runtime.tool_discovery, "handle_skill_list", slow_skill_list)

    runtime = ToolLoopRuntime(
        conversation_id=1,
        owner_id=1,
        policy=RuntimePolicy(
            max_tool_rounds=1,
            enable_single_pass_streaming_tools=True,
            fast_tool_timeout_seconds=0.02,
        ),
    )
    messages = [{"role": "user", "content": "list skills"}]
    events: list[object] = []

    async for event in runtime.run(
        messages,
        [{"type": "function", "function": {"name": "skill_list"}}],
        _FakeSink(),  # type: ignore[arg-type]
    ):
        events.append(event)

    decoded_events = [_decode_sse_event(event) for event in events]
    heartbeat_nodes = [
        (event.get("node"), event.get("status"))
        for event in decoded_events
        if event and event.get("type") == "tool_heartbeat"
    ]
    assert ("policy_check", "started") in heartbeat_nodes
    assert ("skill_list", "started") in heartbeat_nodes
    assert ("tool_execution", "timeout") in heartbeat_nodes
    assert any(
        event
        and event.get("type") == "tool_result"
        and event.get("error_class") == "timeout"
        and event.get("hard_failure") is True
        for event in decoded_events
    )
