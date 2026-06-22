"""Agent 侧模型兼容层。只调用框架网关对象，不修改框架 adapter。"""
import json
import re
import uuid

from app.gateway.router import gateway_router


def parse_inline_tool_calls(content: str) -> tuple[str, list[dict]]:
    """当模型把 XML 式工具调用写进 content 正文时，从中解析出标准 tool_calls。

    兼容变体：
    - <invoke name="...">...</invoke> (原生)
    - <antml:invoke name="...">...</antml:invoke> (Anthropic 风格)
    - <tool_call>...</tool_call> 容器内的 invoke
    - ｜invoke name="...">...</｜invoke> （全角竖线前缀）
    - 大小写、多余空白、换行都容错

    Returns: (clean_content, tool_calls_list)
    """
    if not content:
        return content, []

    # 识别整个工具调用块的范围（从第一个 invoke/tool_call 标记开始，到最后一个闭合标记结束）
    # 兼容各种前缀变体：antml:invoke、｜invoke、invoke 等
    _prefix = r'(?:\w+[\:\|])?'
    start_pattern = re.compile(
        rf'(?:<{_prefix}invoke\s+name=|<{_prefix}tool_call>)',
        re.IGNORECASE,
    )
    match = start_pattern.search(content)
    if not match:
        return content, []

    # 提取所有工具调用
    _prefix_inner = r'(?:\w+[\:\|])?'
    tool_calls = []
    invoke_pattern = re.compile(
        rf'<{_prefix}invoke\s+name=[\"\']([^\"\']+)[\"\']\s*>'
        r'(.*?)'
        rf'</{_prefix}invoke\s*>',
        re.IGNORECASE | re.DOTALL,
    )

    for im in invoke_pattern.finditer(content):
        tool_name = im.group(1).strip()
        inner_xml = im.group(2)

        # 从 inner_xml 提取所有 parameter
        param_pattern = re.compile(
            rf'<{_prefix_inner}parameter\s+name=[\"\']([^\"\']+)[\"\']'
            r'(?:\s+string=[\"\'](true|false)[\"\'])?\s*>'
            r'(.*?)'
            rf'</{_prefix_inner}parameter\s*>',
            re.IGNORECASE | re.DOTALL,
        )

        args = {}
        for pm in param_pattern.finditer(inner_xml):
            pname = pm.group(1).strip()
            raw_val = pm.group(3).strip()
            string_hint = pm.group(2)
            # string=false → 尝试 JSON 解析
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

    # 逐个移除每个 invoke 块，保留块外正文
    close_pattern = re.compile(
        rf'</(?:\w+[\:\|])?invoke\s*>',
        re.IGNORECASE,
    )
    # 找到每个完整 invoke 块的起止位置
    block_boundaries = []
    for im in invoke_pattern.finditer(content):
        block_boundaries.append((im.start(), im.end()))
    if not block_boundaries:
        return content, tool_calls

    # 逆序移除（保持索引不变）
    clean_parts = list(content)
    for start, end in reversed(block_boundaries):
        clean_parts[start:end] = ''

    clean_content = ''.join(clean_parts).strip()
    clean_content = re.sub(r'\n{3,}', '\n\n', clean_content).strip()

    return clean_content, tool_calls


def _extract_raw_tool_calls(raw: dict) -> list[dict]:
    choices = raw.get("choices") or []
    if not choices:
        return []
    message = choices[0].get("message") or {}
    result = []
    for item in message.get("tool_calls") or []:
        fn = item.get("function") or {}
        args = fn.get("arguments") or {}
        if isinstance(args, str):
            try:
                args = json.loads(args)
            except json.JSONDecodeError:
                args = {}
        result.append({
            "id": item.get("id", ""),
            "type": item.get("type", "function"),
            "function": {
                "name": fn.get("name", ""),
                "arguments": args,
            },
        })
    return result


def final_clean_content(content: str) -> str:
    """最终兜底清理：移除 content 中残留的 XML 式工具调用标记。

    防止模型把 <invoke> / <antml:invoke> / <tool_call> 等 DSML 标记
    泄漏到持久化的消息内容中。作为 parse_inline_tool_calls 的补充兜底。
    """
    if not content:
        return content
    # 移除带各种命名空间前缀的 invoke 块
    cleaned = re.sub(
        r'<\w*:?invoke\s+name=.*?</\w*:?invoke\s*>',
        '', content, flags=re.IGNORECASE | re.DOTALL
    )
    # 移除 tool_call 容器
    cleaned = re.sub(
        r'<\w*:?tool_call\s*>.*?</\w*:?tool_call\s*>',
        '', cleaned, flags=re.IGNORECASE | re.DOTALL
    )
    # 压缩多余空行
    cleaned = re.sub(r'\n{3,}', '\n\n', cleaned).strip()
    return cleaned


async def recover_tool_calls(messages: list[dict], profile_key: str, tools: list[dict]) -> dict:
    """当框架 adapter 漏抽 tool_calls 时，从 raw OpenAI-compatible 响应恢复。"""
    profile = gateway_router.get_profile(profile_key)
    provider = gateway_router.get_provider(profile["provider"])
    raw = await provider.chat(
        messages=messages,
        model=profile["model"],
        temperature=profile["temperature"],
        max_tokens=profile["max_tokens"],
        tools=tools,
    )
    choices = raw.get("choices") or []
    message = (choices[0].get("message") if choices else {}) or {}
    finish_reason = choices[0].get("finish_reason", "stop") if choices else "stop"
    return {
        "content": message.get("content", ""),
        "thinking": message.get("reasoning_content", ""),
        "tool_calls": _extract_raw_tool_calls(raw),
        "finish_reason": finish_reason,
    }
