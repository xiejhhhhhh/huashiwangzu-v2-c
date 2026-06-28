"""Agent 侧模型兼容层。只调用框架网关对象，不修改框架 adapter。

Adapter fix 后（2025-06）deepseek-v4-flash 的 tool_calls 已由
DeepSeekAdapter 正确提取并返回，本节函数降级为兜底/清理层：
- parse_inline_tool_calls: 当工具调用标记（<invoke>...）泄漏到 content 正文时解析
- final_clean_content: 持久化前清理残留标记
- recover_tool_calls: 极端情况下 adapter 仍漏抽时的恢复手段（会额外消耗一次 API）
"""
import json
import logging
import re
import uuid

from app.gateway.router import gateway_router

logger = logging.getLogger("v2.agent").getChild("model_client")


def _normalize_inline_markup(content: str) -> str:
    normalized = content
    normalized = normalized.replace("<｜｜DSML｜｜", "<")
    normalized = normalized.replace("</｜｜DSML｜｜", "</")
    for tag in ("tool_call", "tool_calls", "invoke", "parameter"):
        normalized = normalized.replace(f"<｜{tag}", f"<{tag}")
        normalized = normalized.replace(f"</｜{tag}", f"</{tag}")
        normalized = normalized.replace(f"｜{tag}", f"<{tag}")
        normalized = normalized.replace(f"</｜{tag}", f"</{tag}")
    return normalized


def _strip_tool_call_containers(content: str) -> str:
    return re.sub(
        r'</?\w*:?tool_calls?\s*>',
        '', content, flags=re.IGNORECASE | re.DOTALL,
    )


def _normalize_tool_calls(tool_calls: list[dict]) -> list[dict]:
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


def parse_inline_tool_calls(content: str) -> tuple[str, list[dict]]:
    """当模型把 XML 式工具调用写进 content 正文时，从中解析出标准 tool_calls。

    兼容变体：
    - <invoke name="...">...</invoke>
    - <antml:invoke name="...">...</antml:invoke>
    - <tool_call>...</tool_call> / <tool_calls>...</tool_calls> 容器内的 invoke
    - <｜｜DSML｜｜tool_calls>...<｜｜DSML｜｜invoke>...</｜｜DSML｜｜invoke>...</｜｜DSML｜｜tool_calls>
    - ｜invoke name="...">...</｜invoke> （全角竖线前缀）
    - 大小写、多余空白、换行都容错

    Returns: (clean_content, tool_calls_list)
    """
    if not content:
        return content, []

    content = _normalize_inline_markup(content)

    invoke_re = re.compile(
        r'<\w*:?invoke\s+name=[\"\']([^\"\']+)[\"\']\s*>(.*?)</\w*:?invoke\s*>',
        re.IGNORECASE | re.DOTALL,
    )
    param_re = re.compile(
        r'<\w*:?parameter\s+name=[\"\']([^\"\']+)[\"\']'
        r'(?:\s+string=[\"\'](true|false)[\"\'])?\s*>(.*?)</\w*:?parameter\s*>',
        re.IGNORECASE | re.DOTALL,
    )

    tool_calls = []
    for m in invoke_re.finditer(content):
        tool_name = m.group(1).strip()
        inner = m.group(2)
        args = {}
        for pm in param_re.finditer(inner):
            pname = pm.group(1).strip()
            raw_val = pm.group(3).strip()
            string_hint = pm.group(2)
            if string_hint and string_hint.lower() == "false":
                try:
                    args[pname] = json.loads(raw_val)
                except (json.JSONDecodeError, TypeError):
                    args[pname] = raw_val
            else:
                args[pname] = raw_val
        tool_calls.append({
            "id": f"call_inline_{uuid.uuid4().hex[:12]}",
            "type": "function",
            "function": {"name": tool_name, "arguments": args},
        })

    if not tool_calls:
        return content, tool_calls

    clean = invoke_re.sub('', content).strip()
    clean = _strip_tool_call_containers(clean)
    clean = re.sub(r'\n{3,}', '\n\n', clean).strip()
    return clean, tool_calls


def final_clean_content(content: str) -> str:
    """最终兜底清理：移除 content 中残留的 XML 式工具调用标记。

    作为 parse_inline_tool_calls 的补充。
    """
    if not content:
        return content
    content = _normalize_inline_markup(content)
    cleaned = re.sub(
        r'<\w*:?invoke\s+name=.*?</\w*:?invoke\s*>',
        '', content, flags=re.IGNORECASE | re.DOTALL,
    )
    cleaned = re.sub(
        r'<\w*:?tool_calls?\s*>.*?</\w*:?tool_calls?\s*>',
        '', cleaned, flags=re.IGNORECASE | re.DOTALL,
    )
    cleaned = _strip_tool_call_containers(cleaned)
    cleaned = re.sub(r'\n{3,}', '\n\n', cleaned).strip()
    return cleaned


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
