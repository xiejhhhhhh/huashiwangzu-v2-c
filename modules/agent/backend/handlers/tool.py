"""Tool execution and capability registration for agent module.

Registered capabilities:
  - agent:get_system_prompt / update_system_prompt
  - agent:get_enterprise_prompt / update_enterprise_prompt
  - agent:get_my_profile / update_my_profile
  - agent:spawn_subagent
"""

from __future__ import annotations

import json
import logging

from app.core.exceptions import PermissionDenied
from app.gateway.router import gateway_router
from app.services.module_registry import register_capability

from ..services import conversation_service as conv_svc
from ..services import tool_discovery
from ..services.model_client import parse_inline_tool_calls, final_clean_content

logger = logging.getLogger("v2.agent").getChild("handlers.tool")

SUBAGENT_MAX_ROUNDS = 4
SUBAGENT_CONTEXT_LIMIT = 10


# ── Helpers ──

def _j(obj) -> str:
    return json.dumps(obj, ensure_ascii=False, default=str)


def _resolve_user_id(caller: str) -> int:
    """caller: user:{id} → int user_id。"""
    try:
        prefix, raw_id = caller.split(":", 1)
        if prefix == "user":
            return int(raw_id)
    except (TypeError, ValueError):
        pass
    raise PermissionDenied("Invalid caller")


def _tool_calls_for_history(tool_calls: list[dict]) -> list[dict]:
    normalized = []
    for item in tool_calls:
        fn = item.get("function", item)
        args = fn.get("arguments") or {}
        if not isinstance(args, str):
            args = _j(args)
        normalized.append({
            "id": item.get("id", ""),
            "type": item.get("type", "function"),
            "function": {
                "name": fn.get("name", ""),
                "arguments": args,
            },
        })
    return normalized


# ── Capability: agent:get_system_prompt ──

async def _cap_get_system_prompt(params: dict, caller: str) -> dict:
    """读取系统提示词（仅 admin）。"""
    from app.database import AsyncSessionLocal
    async with AsyncSessionLocal() as db:
        content = await conv_svc.get_system_prompt(db)
        return {"content": content}


async def _cap_update_system_prompt(params: dict, caller: str) -> dict:
    """更新系统提示词（仅 admin）。"""
    from app.database import AsyncSessionLocal
    content = params.get("content", "")
    if not content:
        return {"error": "content is required"}
    async with AsyncSessionLocal() as db:
        caller_uid = _resolve_user_id(caller)
        prompt = await conv_svc.update_system_prompt(db, content, caller_uid)
        return {"id": prompt.id, "content": prompt.content, "version": prompt.version}


async def _cap_get_enterprise_prompt(params: dict, caller: str) -> dict:
    """读取企业提示词（仅 admin）。"""
    from app.database import AsyncSessionLocal
    async with AsyncSessionLocal() as db:
        content = await conv_svc.get_enterprise_prompt(db)
        return {"content": content}


async def _cap_update_enterprise_prompt(params: dict, caller: str) -> dict:
    """更新企业提示词（仅 admin）。"""
    from app.database import AsyncSessionLocal
    content = params.get("content", "")
    if not content:
        return {"error": "content is required"}
    async with AsyncSessionLocal() as db:
        caller_uid = _resolve_user_id(caller)
        prompt = await conv_svc.update_enterprise_prompt(db, content, caller_uid)
        return {"id": prompt.id, "content": prompt.content, "version": prompt.version}


async def _cap_get_my_profile(params: dict, caller: str) -> dict:
    """读取自己的个人画像。"""
    from app.database import AsyncSessionLocal
    owner_id = _resolve_user_id(caller)
    async with AsyncSessionLocal() as db:
        from ..init_db import ensure_user_profile
        profile = await ensure_user_profile(db, owner_id)
        return {
            "owner_id": profile.owner_id,
            "profile_data": json.loads(profile.profile_data) if profile.profile_data else {},
            "version": profile.version,
            "evolved_at": profile.evolved_at.isoformat() if profile.evolved_at else None,
            "conversation_count": profile.conversation_count,
        }


async def _cap_update_my_profile(params: dict, caller: str) -> dict:
    """更新自己的个人画像（仅能改自己的，owner 从 caller 解析）。"""
    from app.database import AsyncSessionLocal
    profile_data = params.get("profile_data")
    if not profile_data or not isinstance(profile_data, dict):
        return {"error": "profile_data (dict) is required"}
    owner_id = _resolve_user_id(caller)
    async with AsyncSessionLocal() as db:
        profile = await conv_svc.update_user_profile(db, owner_id, profile_data)
        return {
            "owner_id": profile.owner_id,
            "profile_data": json.loads(profile.profile_data) if profile.profile_data else {},
            "version": profile.version,
        }


# ── Capability: agent:spawn_subagent ──

async def _cap_spawn_subagent(params: dict, caller: str) -> dict:
    """子 Agent：把子任务委托给一个独立工具循环，拿回结论。"""
    task = params.get("task", "")
    if not task or not isinstance(task, str):
        return {"error": "task is required"}

    caller_role = "viewer"
    extra_tools = params.get("tools") or []
    extra_context = params.get("context") or ""

    try:
        system_prompt = (
            "你是一个子 Agent，专注于完成一项具体任务，然后返回结论。\n\n"
            f"任务：{task}\n\n"
        )
        if extra_context:
            system_prompt += f"参考上下文：\n{extra_context}\n\n"
        system_prompt += (
            "规则：\n"
            "1. 使用可用工具完成任务，不要闲聊。\n"
            f"2. 最多 {SUBAGENT_MAX_ROUNDS} 轮工具调用，超限则返回已有结论。\n"
            "3. 完成目标后，清晰总结结论。\n"
            "4. 如果工具调用失败，尝试替代方案。\n"
            "5. 用中文回答。"
        )

        tools = tool_discovery.build_tools(caller_role)
        if extra_tools:
            allowed = set(extra_tools) | {"skill_list", "skill_describe", "skill_use"}
            tools = [t for t in tools if t.get("function", {}).get("name", "") in allowed]

        messages = [{"role": "system", "content": system_prompt}]

        full_content = ""
        for _round in range(SUBAGENT_MAX_ROUNDS):
            kwargs = {"messages": messages, "tools": tools}
            result = await gateway_router.chat(**kwargs)

            if result.get("error"):
                full_content = f"子 Agent 执行出错：{result['error']}"
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

                if name == "skill_list":
                    tool_result = await tool_discovery.handle_skill_list(args, caller_role)
                elif name == "skill_describe":
                    tool_result = await tool_discovery.handle_skill_describe(args, caller_role)
                elif name == "skill_use":
                    tool_result = await tool_discovery.handle_skill_use(args, caller=caller, caller_role=caller_role)
                else:
                    from app.services.module_registry import call_capability
                    module_key, action = tool_discovery.parse_tool_name(name)
                    tool_result = await call_capability(
                        module_key, action, args, caller=caller, caller_role=caller_role,
                    )

                messages.append({
                    "role": "tool",
                    "name": name,
                    "content": _j(tool_result),
                    "tool_call_id": tc.get("id", ""),
                })

        if not full_content:
            for msg in reversed(messages):
                if msg["role"] == "assistant":
                    full_content = msg.get("content", "") or ""
                    break

        full_content = final_clean_content(full_content)

        return {
            "success": True,
            "data": {
                "conclusion": full_content or "子 Agent 未生成结论",
                "rounds_used": _round + 1,
                "messages_count": len(messages),
            },
        }
    except Exception as exc:
        return {"error": f"子 Agent 执行异常：{exc}"}


# ── Register capabilities ──

register_capability(
    "agent", "get_system_prompt", _cap_get_system_prompt,
    description="读取当前系统提示词（管理员权限）。系统提示词定义了 Agent 的核心行为、知识库使用规则和联网能力规则。",
    brief="读取系统提示词",
    parameters={},
    min_role="admin",
)
register_capability(
    "agent", "update_system_prompt", _cap_update_system_prompt,
    description="更新系统提示词（管理员权限）。当管理员用户要求修改 Agent 底层行为规则时调用此工具。",
    brief="更新系统提示词",
    parameters={"content": {"type": "string", "description": "新的系统提示词内容"}},
    min_role="admin",
)
register_capability(
    "agent", "get_enterprise_prompt", _cap_get_enterprise_prompt,
    description="读取当前企业提示词（管理员权限）。企业提示词包含了公司背景、业务规则等企业上下文信息。",
    brief="读取企业提示词",
    parameters={},
    min_role="admin",
)
register_capability(
    "agent", "update_enterprise_prompt", _cap_update_enterprise_prompt,
    description="更新企业提示词（管理员权限）。当管理员用户要求修改公司/企业背景设定时调用此工具。",
    brief="更新企业提示词",
    parameters={"content": {"type": "string", "description": "新的企业提示词内容"}},
    min_role="admin",
)
register_capability(
    "agent", "get_my_profile", _cap_get_my_profile,
    description="读取当前用户的个人画像。个人画像包含用户的语气偏好、禁忌话题、关注领域和习惯，是系统自动学习的个性化配置。",
    brief="读取我的画像",
    parameters={},
    min_role="viewer",
)
register_capability(
    "agent", "update_my_profile", _cap_update_my_profile,
    description="更新当前用户的个人画像（仅能改自己的）。当用户要求修改自己的语气偏好、设定或个性化配置时调用此工具。owner 固定为当前用户，不允许修改他人画像。",
    brief="更新我的画像",
    parameters={
        "profile_data": {
            "type": "object",
            "description": "画像数据字典，包含 tone（语气偏好，字符串）、taboos（禁忌话题，字符串数组）、focus（关注领域，字符串数组）、habits（习惯描述，字符串数组）",
            "properties": {
                "tone": {"type": "string", "description": "语气偏好，如'简洁'、'专业'、'友好'"},
                "taboos": {"type": "array", "items": {"type": "string"}, "description": "禁忌话题列表"},
                "focus": {"type": "array", "items": {"type": "string"}, "description": "关注领域列表"},
                "habits": {"type": "array", "items": {"type": "string"}, "description": "习惯描述列表"},
            },
        },
    },
    min_role="viewer",
)
register_capability(
    "agent", "spawn_subagent", _cap_spawn_subagent,
    description="把子任务委托给一个独立子 Agent 执行并拿回结论。子 Agent 会用自己的工具循环执行任务，完成后返回结论。适用于拆解复杂任务（如同时查资料、生图、整理文档）。",
    brief="委托子Agent执行任务",
    parameters={
        "task": {"type": "string", "description": "任务描述，说明子Agent需要完成什么"},
        "tools": {"type": "array", "items": {"type": "string"}, "description": "限定可用技能列表（可选），如 ['web-tools__search', 'image-gen__generate']"},
        "context": {"type": "string", "description": "额外上下文（可选），如已有信息或参考数据"},
    },
    min_role="viewer",
)
