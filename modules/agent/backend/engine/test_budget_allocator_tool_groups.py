"""Tests for atomic tool-round preservation in budget trimming."""

from .budget_allocator import _group_projected_messages


def test_group_projected_messages_keeps_tool_round_atomic():
    messages = [
        {"role": "system", "content": "sys"},
        {
            "role": "assistant",
            "content": "",
            "tool_calls": [
                {
                    "id": "call_1",
                    "type": "function",
                    "function": {"name": "skill_use", "arguments": {"name": "knowledge__search"}},
                }
            ],
        },
        {"role": "tool", "tool_call_id": "call_1", "content": "{\"skills\": []}"},
        {"role": "user", "content": "next"},
    ]

    grouped = _group_projected_messages(messages)

    assert len(grouped) == 3
    assert grouped[1][0]["role"] == "assistant"
    assert grouped[1][0]["tool_calls"][0]["function"]["name"] == "skill_use"
    assert grouped[1][1]["role"] == "tool"
    assert grouped[2][0]["role"] == "user"
