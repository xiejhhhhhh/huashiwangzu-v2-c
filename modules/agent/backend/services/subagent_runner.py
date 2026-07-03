"""子 Agent 单任务执行器（从 _cap_spawn_subagent 提取）。

职责单一：
1. 接收一个 task 描述，构造 system prompt
2. 工具过滤 + 读写守卫
3. 运行 tool loop（可重入、可重试）
4. 返回 task_result dict
"""
from __future__ import annotations

import json
import logging

from app.database import AsyncSessionLocal
from app.gateway.router import gateway_router

from ..prompt_seeds import SUBAGENT_SYSTEM_KEY
from ..services import tool_discovery
from ..services.runtime_prompt_provider import render_system_prompt
from .model_client import final_clean_content, parse_inline_tool_calls

logger = logging.getLogger("v2.agent").getChild("subagent_runner")

READ_ONLY_TOOLS = {"skill_list", "skill_describe"}
_READ_PREFIXES = ("knowledge__", "memory__recall", "web-tools__", "desktop-tools__")

SUBAGENT_MAX_ROUNDS = 4


def _is_read_only_tool(name: str) -> bool:
    if name in READ_ONLY_TOOLS:
        return True
    for prefix in _READ_PREFIXES:
        if name.startswith(prefix):
            return True
    return False


def _is_allowed_without_write(name: str, args: dict) -> bool:
    if name == "skill_use":
        target_name = str(args.get("name") or "")
        return _is_read_only_tool(target_name)
    return _is_read_only_tool(name)


def _tool_result_error(result: object) -> str | None:
    if not isinstance(result, dict):
        return None
    if result.get("success") is False:
        return str(result.get("error") or "success=false")
    if result.get("error"):
        return str(result["error"])
    inner = result.get("data", result)
    if isinstance(inner, dict):
        if inner.get("success") is False:
            return str(inner.get("error") or "success=false")
        if inner.get("error"):
            return str(inner["error"])
    return None


def _j(obj) -> str:
    return json.dumps(obj, ensure_ascii=False, default=str)


def _tool_calls_for_history(tool_calls: list[dict]) -> list[dict]:
    """Normalize tool calls for LLM history."""
    normalized = []
    for item in tool_calls:
        fn = item.get("function", item)
        args = fn.get("arguments") or {}
        if not isinstance(args, str):
            args = _j(args)
        normalized.append({
            "id": item.get("id", ""),
            "type": item.get("type", "function"),
            "function": {"name": fn.get("name", ""), "arguments": args},
        })
    return normalized


async def _build_system_prompt(
    task_desc: str,
    combined_context: str = "",
    task_write_enabled: bool = False,
    max_rounds: int = SUBAGENT_MAX_ROUNDS,
) -> str:
    """构建子 Agent system prompt。"""
    context_section = f"参考上下文：\n{combined_context[:2000]}\n\n" if combined_context else ""
    write_guard_section = "" if task_write_enabled else "注意：你只能使用读/检索类工具，不能修改或写入数据。\n"
    async with AsyncSessionLocal() as db:
        return await render_system_prompt(
            db,
            SUBAGENT_SYSTEM_KEY,
            {
                "task_desc": task_desc,
                "context_section": context_section,
                "write_guard_section": write_guard_section,
                "max_rounds": max_rounds,
            },
        )


async def run_single_task(
    task_desc: str,
    task_context: str = "",
    extra_context: str = "",
    base_tools: list | None = None,
    task_tools_param: list | None = None,
    task_write_enabled: bool = False,
    max_rounds: int = SUBAGENT_MAX_ROUNDS,
    caller: str = "",
    caller_role: str = "viewer",
    owner_id: int | None = None,
    retry_prompt: str = "",
) -> dict:
    """执行一个子 Agent 任务，返回 task_result。

    可重入设计：gate 校验失败后，调用方传入 retry_prompt，
    会在 messages 中追加一条 user 消息要求修正。
    """
    combined = (
        f"{extra_context}\n\n{task_context}"
        if extra_context and task_context
        else (task_context or extra_context or "")
    )
    system_prompt = await _build_system_prompt(
        task_desc, combined, task_write_enabled, max_rounds,
    )

    # 工具过滤
    filtered = base_tools or tool_discovery.build_tools(caller_role)
    if task_tools_param:
        allowed = set(task_tools_param) | READ_ONLY_TOOLS
        task_tools = [t for t in filtered
                      if t.get("function", {}).get("name", "") in allowed]
    else:
        task_tools = filtered

    # 构造初始 messages（retry_prompt 非空表示这是重试）
    messages = [{"role": "system", "content": system_prompt}]
    if retry_prompt:
        messages.append({"role": "user", "content": retry_prompt})

    return await _execute_tool_loop(
        messages=messages,
        task_tools=task_tools,
        max_rounds=max_rounds,
        task_write_enabled=task_write_enabled,
        caller=caller,
        caller_role=caller_role,
        owner_id=owner_id,
        task_desc=task_desc,
    )


async def _execute_tool_loop(
    messages: list[dict],
    task_tools: list[dict],
    max_rounds: int,
    task_write_enabled: bool,
    caller: str,
    caller_role: str,
    owner_id: int | None,
    task_desc: str,
) -> dict:
    """内部工具循环 — 可被 gate 重试复用（传入更多 messages）。"""
    full_content = ""
    rounds_used = 0
    task_error = None
    tool_error = None
    tool_call_trace: list[dict] = []
    tool_result_trace: list[dict] = []

    for _round in range(max_rounds):
        tool_cfg = (
            {"messages": messages, "tools": task_tools}
            if task_tools
            else {"messages": messages}
        )
        result = await gateway_router.chat(**tool_cfg)

        if result.get("error"):
            task_error = result["error"]
            break

        content = result.get("content", "")
        tool_calls = result.get("tool_calls") or []

        if not tool_calls:
            clean_content, inline_calls = parse_inline_tool_calls(content)
            if inline_calls:
                result["content"] = clean_content
                tool_calls = inline_calls

        if not tool_calls:
            full_content = content
            rounds_used = _round + 1
            break

        messages.append({
            "role": "assistant",
            "content": content,
            "tool_calls": _tool_calls_for_history(tool_calls),
        })

        for tc in tool_calls:
            fn = tc.get("function", tc)
            name = fn.get("name", "")
            try:
                args = fn.get("arguments") or {}
                if isinstance(args, str):
                    args = json.loads(args)
            except Exception:
                args = {}
            tool_call_id = str(tc.get("id", "") or "")
            tool_call_trace.append({
                "round": _round + 1,
                "name": name,
                "tool_call_id": tool_call_id,
                "arguments": args,
            })

            if not task_write_enabled and not _is_allowed_without_write(name, args):
                blocked_name = str(args.get("name") or name) if name == "skill_use" else name
                tool_result = {
                    "error": f"工具 '{blocked_name}' 需要写入权限，当前未启用。请在调用时设置 write_enabled=True",
                }
            elif name == "skill_list":
                tool_result = await tool_discovery.handle_skill_list(args, caller_role)
            elif name == "skill_describe":
                tool_result = await tool_discovery.handle_skill_describe(
                    args,
                    caller_role,
                    owner_id=owner_id,
                    agent_code="subagent",
                )
            elif name == "skill_use":
                tool_result = await tool_discovery.handle_skill_use(
                    args, caller=caller, caller_role=caller_role,
                )
            else:
                from app.services.module_registry import call_capability
                module_key, action = tool_discovery.parse_tool_name(name)
                tool_result = await call_capability(
                    module_key, action, args, caller=caller, caller_role=caller_role,
                )
            tool_result_trace.append({
                "round": _round + 1,
                "name": name,
                "tool_call_id": tool_call_id,
                "result": tool_result,
            })
            tool_error = tool_error or _tool_result_error(tool_result)

            messages.append({
                "role": "tool",
                "name": name,
                "content": _j(tool_result),
                "tool_call_id": tool_call_id,
            })

    if not full_content:
        for msg in reversed(messages):
            if msg["role"] == "assistant":
                full_content = msg.get("content", "") or ""
                break

    full_content = final_clean_content(full_content)
    if not full_content and tool_error and not task_error:
        task_error = tool_error

    return {
        "task": task_desc,
        "status": "error" if task_error else "completed",
        "error": task_error,
        "conclusion": full_content or "子 Agent 未生成结论",
        "rounds_used": rounds_used,
        "tool_calls": tool_call_trace,
        "tool_results": tool_result_trace,
    }
