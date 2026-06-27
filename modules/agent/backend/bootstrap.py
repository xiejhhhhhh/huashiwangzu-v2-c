"""Agent module bootstrap: single entry point for initialization, task registration,
and capability registration.

Called once at module load time from router.py. Consolidates all side-effect-driven
setup so the router file only owns API routing — not lifecycle management."""

import logging

from app.services.module_registry import register_capability
from app.services.task_worker import register_task_handler

logger = logging.getLogger("v2.agent").getChild("bootstrap")


def register_agent_tasks() -> None:
    """Register all background task handlers."""
    from .services.profile_evolve import handle_profile_evolve
    from .handlers.tasks import _handle_memory_dream, _handle_memory_distill, _handle_slow_tool

    register_task_handler("profile_evolve", handle_profile_evolve)
    register_task_handler("memory_dream", _handle_memory_dream)
    register_task_handler("memory_distill", _handle_memory_distill)
    register_task_handler("agent_execute_slow_tool", _handle_slow_tool)
    logger.info("Agent task handlers registered (profile_evolve, memory_dream, memory_distill, agent_execute_slow_tool)")


def register_agent_capabilities() -> None:
    """Register all cross-module capabilities."""
    from .handlers.tool import (
        _cap_get_system_prompt, _cap_update_system_prompt,
        _cap_get_enterprise_prompt, _cap_update_enterprise_prompt,
        _cap_get_my_profile, _cap_update_my_profile,
        _cap_spawn_subagent, _cap_skill_manage,
        _cap_get_role_profiles, _cap_get_role_profile, _cap_upsert_role_profile,
        _cap_get_enterprise_profile, _cap_upsert_enterprise_profile,
        _cap_list_market_profiles, _cap_upsert_market_profile,
        _cap_record_profile_signal, _cap_list_profile_signals,
        _cap_record_trajectory, _cap_list_trajectories,
    )

    capabilities = [
        ("agent", "get_system_prompt", _cap_get_system_prompt,
         "读取当前系统提示词（管理员权限）。系统提示词定义了 Agent 的核心行为、知识库使用规则和联网能力规则。",
         "读取系统提示词", {}, "admin"),
        ("agent", "update_system_prompt", _cap_update_system_prompt,
         "更新系统提示词（管理员权限）。当管理员用户要求修改 Agent 底层行为规则时调用此工具。",
         "更新系统提示词", {"content": {"type": "string", "description": "新的系统提示词内容"}}, "admin"),
        ("agent", "get_enterprise_prompt", _cap_get_enterprise_prompt,
         "读取当前企业提示词（管理员权限）。企业提示词包含了公司背景、业务规则等企业上下文信息。",
         "读取企业提示词", {}, "admin"),
        ("agent", "update_enterprise_prompt", _cap_update_enterprise_prompt,
         "更新企业提示词（管理员权限）。当管理员用户要求修改公司/企业背景设定时调用此工具。",
         "更新企业提示词", {"content": {"type": "string", "description": "新的企业提示词内容"}}, "admin"),
        ("agent", "get_my_profile", _cap_get_my_profile,
         "读取当前用户的个人画像。个人画像包含用户的语气偏好、禁忌话题、关注领域和习惯。",
         "读取我的画像", {}, "viewer"),
        ("agent", "update_my_profile", _cap_update_my_profile,
         "更新当前用户的个人画像（仅能改自己的）。owner 固定为当前用户。",
         "更新我的画像", {
             "profile_data": {
                 "type": "object",
                 "description": "画像数据字典",
                 "properties": {
                     "tone": {"type": "string"},
                     "taboos": {"type": "array", "items": {"type": "string"}},
                     "focus": {"type": "array", "items": {"type": "string"}},
                     "habits": {"type": "array", "items": {"type": "string"}},
                 },
             },
         }, "viewer"),
        ("agent", "spawn_subagent", _cap_spawn_subagent,
         "委托子 Agent 执行任务（支持单任务/批量/工具白名单/上下文压缩/执行轨迹）。默认只给读类工具，写类需设置 write_enabled=True。",
         "委托子Agent执行任务",
         {"task": {"type": "string", "description": "单任务描述"},
          "tasks": {"type": "array", "items": {"type": "object"}, "description": "批量任务列表"},
          "tools": {"type": "array", "items": {"type": "string"}, "description": "限定可用工具名"},
          "context": {"type": "string", "description": "参考上下文"},
          "write_enabled": {"type": "boolean", "description": "是否允许写操作"},
          "track_trajectory": {"type": "boolean", "description": "是否记录执行轨迹"},
          "max_rounds": {"type": "integer", "description": "最大工具轮数"}}, "viewer"),
        ("agent", "skill_manage", _cap_skill_manage,
         "管理技能：列表、创建、更新、删除、扫描、使用统计和来源追溯。"
         "Review fork 产出的技能不能直接修改正式技能，必须走审批。",
         "管理技能",
         {"action": {"type": "string", "description": "list/get/create/update/delete/scan/usage/provenance/pending-approvals/approve/reject"},
          "name": {"type": "string", "description": "技能名称"},
          "description": {"type": "string", "description": "技能描述"},
          "body": {"type": "string", "description": "技能内容"},
          "allowed_tools": {"type": "array", "items": {"type": "string"}, "description": "允许的工具列表"},
          "scope": {"type": "string", "description": "作用域 global/project/workspace"}}, "admin"),
        # Profile 2.0 capabilities
        ("agent", "get_role_profiles", _cap_get_role_profiles,
         "列出所有岗位/角色画像，含语气、偏好、工具限制。",
         "列出岗位画像", {}, "viewer"),
        ("agent", "get_role_profile", _cap_get_role_profile,
         "获取指定岗位/角色的详细画像。",
         "查看岗位画像",
         {"role_key": {"type": "string", "description": "岗位标识"}}, "viewer"),
        ("agent", "upsert_role_profile", _cap_upsert_role_profile,
         "创建或更新岗位/角色画像（管理员权限）。",
         "管理岗位画像",
         {"role_key": {"type": "string"}, "role_name": {"type": "string"},
          "tone": {"type": "string"}, "taboos": {"type": "array", "items": {"type": "string"}},
          "focus_areas": {"type": "array", "items": {"type": "string"}},
          "allowed_tools": {"type": "array", "items": {"type": "string"}}}, "admin"),
        ("agent", "get_enterprise_profile", _cap_get_enterprise_profile,
         "获取企业级画像：语气、业务规则、沟通风格等。",
         "查看企业画像", {}, "viewer"),
        ("agent", "upsert_enterprise_profile", _cap_upsert_enterprise_profile,
         "创建或更新企业级画像（管理员权限）。",
         "管理企业画像",
         {"enterprise_name": {"type": "string"}, "tone": {"type": "string"},
          "business_rules": {"type": "array", "items": {"type": "string"}},
          "communication_style": {"type": "string"}}, "admin"),
        ("agent", "list_market_profiles", _cap_list_market_profiles,
         "列出市场/产品/品牌/竞品画像。",
         "列出市场画像",
         {"profile_type": {"type": "string", "description": "可选过滤：product/brand/competitor"}}, "viewer"),
        ("agent", "upsert_market_profile", _cap_upsert_market_profile,
         "创建或更新市场/产品/品牌/竞品画像（管理员权限）。",
         "管理市场画像",
         {"profile_type": {"type": "string"}, "key": {"type": "string"},
          "name": {"type": "string"}, "attributes": {"type": "object"},
          "tags": {"type": "array", "items": {"type": "string"}}}, "admin"),
        ("agent", "record_profile_signal", _cap_record_profile_signal,
         "记录一条低置信度的画像信号，用于后续画像进化。低置信信号不会直接修改正式画像。",
         "记录画像信号",
         {"signal_type": {"type": "string"}, "signal_data": {"type": "object"},
          "confidence": {"type": "number", "description": "0.0-1.0"},
          "target_profile_type": {"type": "string", "description": "user/role/enterprise/market"}}, "viewer"),
        ("agent", "list_profile_signals", _cap_list_profile_signals,
         "列出个人画像信号池中的信号。",
         "查看画像信号",
         {"signal_type": {"type": "string", "description": "可选过滤"},
          "applied": {"type": "boolean", "description": "可选过滤是否已应用"}}, "viewer"),
        # Trajectory capabilities
        ("agent", "record_trajectory", _cap_record_trajectory,
         "记录一次轨迹数据（用户输入/工具调用/结果/纠错等），用于研究和分析。",
         "记录执行轨迹",
         {"session_id": {"type": "string"}, "conversation_id": {"type": "integer"},
          "turn_index": {"type": "integer"}, "user_input": {"type": "string"},
          "tool_calls": {"type": "array"}, "tool_results": {"type": "array"}}, "viewer"),
        ("agent", "list_trajectories", _cap_list_trajectories,
         "列出执行轨迹记录（用于研究分析）。",
         "查看执行轨迹",
         {"conversation_id": {"type": "integer", "description": "可选过滤"},
          "session_id": {"type": "string", "description": "可选过滤"}}, "admin"),
    ]

    for module_key, action, handler, desc, brief, params, min_role in capabilities:
        register_capability(
            module_key, action, handler,
            description=desc, brief=brief, parameters=params, min_role=min_role,
        )
    logger.info("Agent capabilities registered (%d)", len(capabilities))


def init_agent_module() -> None:
    """Initialize the agent module at load time."""
    register_agent_tasks()
    register_agent_capabilities()
    logger.info("Agent module bootstrapped")
