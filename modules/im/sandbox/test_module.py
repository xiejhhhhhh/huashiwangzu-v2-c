"""Sandbox contract tests for the IM module.

The sandbox imports the module through the same ``huashiwangzu_modules``
namespace used by the framework, then validates request models and pure
contract helpers without creating database rows.
"""

from __future__ import annotations

import importlib
import sys
import types
from pathlib import Path
from typing import Protocol

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[3]
BACKEND_DIR = PROJECT_ROOT / "backend"
MODULES_DIR = PROJECT_ROOT / "modules"

for import_path in (BACKEND_DIR, MODULES_DIR):
    path_text = str(import_path)
    if path_text not in sys.path:
        sys.path.insert(0, path_text)


def _init_namespace() -> None:
    if "huashiwangzu_modules" not in sys.modules:
        top_pkg = types.ModuleType("huashiwangzu_modules")
        top_pkg.__path__ = []
        sys.modules["huashiwangzu_modules"] = top_pkg

    pkg_name = "huashiwangzu_modules.im"
    if pkg_name not in sys.modules:
        pkg = types.ModuleType(pkg_name)
        pkg.__path__ = [str(MODULES_DIR / "im" / "backend")]
        sys.modules[pkg_name] = pkg


_init_namespace()
router_mod = importlib.import_module("huashiwangzu_modules.im.router")


class ConversationLike(Protocol):
    member_ids: list[object]


class FakeConversation:
    def __init__(self, member_ids: list[object]) -> None:
        self.member_ids = member_ids


def test_send_message_request_accepts_target_or_conversation() -> None:
    by_conversation = router_mod.SendMessageRequest(conversation_id=42, content=" hello ")
    by_target = router_mod.SendMessageRequest(target_user_id=7, content="hello")

    assert by_conversation.conversation_id == 42
    assert by_target.target_user_id == 7


def test_send_message_request_rejects_invalid_ids() -> None:
    with pytest.raises(ValueError):
        router_mod.SendMessageRequest(conversation_id=0, content="hello")
    with pytest.raises(ValueError):
        router_mod.StartConversationRequest(target_user_id=-1)


def test_content_normalization_rejects_empty_or_non_string_values() -> None:
    with pytest.raises(Exception, match="消息内容不能为空"):
        router_mod._normalize_message_content("   ")
    with pytest.raises(Exception, match="content must be a non-empty string"):
        router_mod._content_param({"content": None})

    assert router_mod._content_param({"content": "  hello  "}) == "hello"


def test_content_normalization_enforces_length_limit() -> None:
    too_long = "x" * (router_mod.MAX_MESSAGE_CONTENT_LENGTH + 1)

    with pytest.raises(Exception, match="消息内容不能超过"):
        router_mod._normalize_message_content(too_long)


def test_mark_read_request_rejects_negative_message_id() -> None:
    with pytest.raises(ValueError):
        router_mod.MarkReadRequest(last_read_message_id=-1)

    assert router_mod.MarkReadRequest(last_read_message_id=0).last_read_message_id == 0


def test_parse_user_id_is_fail_closed() -> None:
    assert router_mod._parse_user_id("user:123") == 123
    assert router_mod._parse_user_id("user:not-a-number") == 0
    assert router_mod._parse_user_id("system:worker") == 0


def test_conversation_members_filters_invalid_json_values() -> None:
    conv: ConversationLike = FakeConversation([1, "2", None, "bad"])

    assert router_mod._conversation_members(conv) == [1, 2]


def main() -> None:
    raise SystemExit(pytest.main([__file__]))


if __name__ == "__main__":
    main()
