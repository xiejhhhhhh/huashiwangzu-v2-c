"""Agent 侧模型兼容层。只调用框架网关对象，不修改框架 adapter。

Adapter fix 后（2025-06）deepseek-v4-flash 的 tool_calls 已由
DeepSeekAdapter 正确提取并返回，本节函数降级为兜底/清理层：
- parse_inline_tool_calls: 当工具调用标记（<invoke>...）泄漏到 content 正文时解析
- final_clean_content: 持久化前清理残留标记
- recover_tool_calls: 极端情况下 adapter 仍漏抽时的恢复手段（会额外消耗一次 API）

核心清洗逻辑已移至 runtime.content_gate，这里保持向后兼容的重导出。
"""
import json
import logging

from app.gateway.router import gateway_router

from ..runtime.content_gate import (
    final_clean_content,  # noqa: F401 — re-exported for backward compat
    parse_inline_tool_calls,  # noqa: F401 — re-exported for backward compat
)

logger = logging.getLogger("v2.agent").getChild("model_client")


def _normalize_tool_calls(tool_calls: list[dict]) -> list[dict]:
    """Normalize raw tool_calls into standard OpenAI format."""
    normalized = []
    for item in tool_calls:
        fn = item.get("function") or item
        args = fn.get("arguments") or {}
        if isinstance(args, str):
            try:
                args = json.loads(args) if args.strip() else {}
            except json.JSONDecodeError:
                args = {}
        if not isinstance(args, dict):
            args = {}
        normalized.append({
            "id": item.get("id") or fn.get("id") or "",
            "type": item.get("type", "function"),
            "function": {"name": fn.get("name", ""), "arguments": args},
        })
    return normalized


async def recover_tool_calls(messages: list[dict], profile_key: str, tools: list[dict]) -> dict:
    """当框架 adapter 漏抽 tool_calls 时，重新发一次请求从中恢复。

    注意：这会额外消耗一次 API 调用（DeepSeek 订阅不计费但仍有延迟）。
    adapter 修对后此函数应极少被触发。
    """
    logger.info("recover_tool_calls triggered — adapter may have missed tool_calls (profile=%s)", profile_key)
    result = await gateway_router.chat(
        messages=messages,
        profile_key=profile_key,
        tools=tools,
    )
    return {
        "content": result.get("content", ""),
        "thinking": result.get("thinking", ""),
        "tool_calls": _normalize_tool_calls(result.get("tool_calls") or []),
        "finish_reason": result.get("finish_reason", "stop"),
        **({"error": result["error"]} if result.get("error") else {}),
    }
