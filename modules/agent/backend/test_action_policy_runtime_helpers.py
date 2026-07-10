"""Regression tests for agent action policy and runtime helper contracts."""

from modules.agent.backend.runtime.tool_loop_runtime import _slow_tool_args
from modules.agent.backend.services.action_policy import (
    _match_sensitive,
    _serialize_tool_args_for_approval,
)


def test_terminal_exec_is_not_outbound_approval_action() -> None:
    assert _match_sensitive("terminal-tools__exec") is False


def test_im_send_is_outbound_approval_action() -> None:
    assert _match_sensitive("im__send") is True


def test_approval_args_are_serialized_and_redacted() -> None:
    payload = _serialize_tool_args_for_approval({"command": "ls", "api_key": "secret-value"})
    assert "ls" in payload
    assert "secret-value" not in payload
    assert "[REDACTED]" in payload


def test_slow_tool_args_unwraps_skill_use_inner_args() -> None:
    tool = {
        "name": "skill_use",
        "slow_name": "image-gen__generate",
        "args": {"name": "image-gen__generate", "args": {"prompt": "city skyline"}},
    }
    assert _slow_tool_args(tool) == {"prompt": "city skyline"}


def test_slow_tool_args_parses_string_inner_args() -> None:
    tool = {
        "name": "skill_use",
        "slow_name": "image-gen__generate",
        "args": {"name": "image-gen__generate", "args": '{"prompt":"mountain"}'},
    }
    assert _slow_tool_args(tool) == {"prompt": "mountain"}
