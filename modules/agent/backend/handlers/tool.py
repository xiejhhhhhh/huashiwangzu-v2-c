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

from app.services.file_reader import resolve_caller_user_id
from app.services.module_registry import register_capability

from ..services import conversation_service as conv_svc
from ..services import tool_discovery

logger = logging.getLogger("v2.agent").getChild("handlers.tool")


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
        caller_uid = resolve_caller_user_id(caller)
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
        caller_uid = resolve_caller_user_id(caller)
        prompt = await conv_svc.update_enterprise_prompt(db, content, caller_uid)
        return {"id": prompt.id, "content": prompt.content, "version": prompt.version}


async def _cap_get_my_profile(params: dict, caller: str) -> dict:
    """读取自己的个人画像。"""
    from app.database import AsyncSessionLocal
    owner_id = resolve_caller_user_id(caller)
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
    owner_id = resolve_caller_user_id(caller)
    async with AsyncSessionLocal() as db:
        profile = await conv_svc.update_user_profile(db, owner_id, profile_data)
        return {
            "owner_id": profile.owner_id,
            "profile_data": json.loads(profile.profile_data) if profile.profile_data else {},
            "version": profile.version,
        }


# ── Capability: agent:spawn_subagent (V2 Enhanced) ──

async def _cap_spawn_subagent(params: dict, caller: str) -> dict:
    """子 Agent V2：批量编排 + 可选 Gate 校验。

    不再自己写工具循环——委托给 SubagentRunner。
    Gate 校验默认关闭（通过 gates: true 启用）。
    """
    from ..services.gate_service import run_gates
    from ..services.subagent_runner import SUBAGENT_MAX_ROUNDS, run_single_task

    caller_role = "viewer"
    owner_id = resolve_caller_user_id(caller) if caller.startswith("user:") else None
    tasks = params.get("tasks") or []
    single_task = params.get("task", "")
    if single_task and not tasks:
        tasks = [{"description": single_task}]
    if not tasks:
        return {"error": "至少需要一个 task 或 tasks 参数"}

    extra_context = params.get("context") or ""
    write_enabled = params.get("write_enabled", False)
    max_rounds = params.get("max_rounds", SUBAGENT_MAX_ROUNDS)
    track_trajectory = params.get("track_trajectory", False)
    enable_gates = params.get("gates", False)
    gate_retry = params.get("gate_retry", 1)

    base_tools = tool_discovery.build_tools(caller_role)
    allowed_tools = params.get("tools") or []
    if allowed_tools:
        allowed_set = set(allowed_tools) | {"skill_list", "skill_describe", "skill_use"}
        base_tools = [t for t in base_tools
                      if t.get("function", {}).get("name", "") in allowed_set]

    results: list[dict] = []
    trajectory: list[dict] = []

    for task_item in tasks:
        desc = task_item.get("description", "") if isinstance(task_item, dict) else str(task_item)
        if not desc:
            continue
        ctx = task_item.get("context", "") if isinstance(task_item, dict) else ""
        task_tools = task_item.get("tools", []) if isinstance(task_item, dict) else []
        task_write = task_item.get("write_enabled", write_enabled) if isinstance(task_item, dict) else write_enabled

        result = await run_single_task(
            task_desc=desc, task_context=ctx, extra_context=extra_context,
            base_tools=base_tools, task_tools_param=task_tools,
            task_write_enabled=task_write, max_rounds=max_rounds,
            caller=caller, caller_role=caller_role, owner_id=owner_id,
        )

        # ── Gate 校验（可选） ──
        if enable_gates and result["status"] == "completed":
            for attempt in range(gate_retry + 1):
                gr = await run_gates(result)
                if gr.passed:
                    break
                has_error = any(i.severity == "error" for i in gr.issues)
                if not has_error:
                    break
                if attempt < gate_retry:
                    prompt_parts = ["你之前的回答未通过质量门控："]
                    prompt_parts.extend(f"- [{i.severity}] {i.message}" for i in gr.issues)
                    prompt_parts.append("\n请修正后重新回答。")
                    result = await run_single_task(
                        task_desc=desc, task_context=ctx, extra_context=extra_context,
                        base_tools=base_tools, task_tools_param=task_tools,
                        task_write_enabled=task_write, max_rounds=max_rounds,
                        caller=caller, caller_role=caller_role,
                        owner_id=owner_id,
                        retry_prompt="\n".join(prompt_parts),
                    )
            result["gate"] = {
                "passed": gr.passed,
                "issues": [
                    {"severity": i.severity, "code": i.code, "message": i.message}
                    for i in gr.issues
                ],
            }

        results.append(result)
        if track_trajectory:
            trajectory.append({
                "task": desc[:200],
                "rounds": result.get("rounds_used", 0),
                "status": result["status"],
            })

    resp: dict[str, object] = {
        "results": results,
        "total_tasks": len(tasks),
        "completed": sum(1 for r in results if r["status"] == "completed"),
        "errors": sum(1 for r in results if r["status"] == "error"),
    }
    if track_trajectory:
        resp["trajectory"] = trajectory
    return resp


# ── Register capabilities ──

# ── Capability: agent:skill_manage ──

async def _cap_skill_manage(params: dict, caller: str) -> dict:
    """Manage skills: list / get / create / update / delete / scan / usage / provenance / pending-approvals / approve / reject."""
    action = params.get("action", "list")
    from app.database import AsyncSessionLocal

    from ..services import skill_governance_service as sgs

    async with AsyncSessionLocal() as db:
        owner_id = resolve_caller_user_id(caller)

        if action == "list":
            scope = params.get("scope")
            enabled_only = params.get("enabled_only", False)
            skills = await sgs.list_skills(db, scope=scope, enabled_only=enabled_only)
            return {"skills": skills, "total": len(skills)}

        elif action == "get":
            name = params.get("name", "")
            if not name:
                return {"error": "name is required"}
            skill = await sgs.get_skill(db, name)
            if not skill:
                return {"error": f"Skill '{name}' not found"}
            return skill

        elif action == "create":
            name = params.get("name", "")
            if not name:
                return {"error": "name is required"}
            result = await sgs.create_skill(
                db, name=name,
                description=params.get("description", ""),
                body=params.get("body", ""),
                allowed_tools=params.get("allowed_tools"),
                paths=params.get("paths"),
                scope=params.get("scope", "global"),
                priority=params.get("priority", 0),
                source="review_proposal" if params.get("from_review") else "manual",
                created_by=owner_id,
            )
            return result

        elif action == "update":
            name = params.get("name", "")
            if not name:
                return {"error": "name is required"}
            result = await sgs.update_skill(
                db, name=name,
                updates={k: v for k, v in params.items() if k in (
                    "description", "body", "scope", "allowed_tools",
                    "paths", "priority", "enabled",
                )},
                updated_by=owner_id,
                from_review=params.get("from_review", False),
            )
            return result

        elif action == "delete":
            name = params.get("name", "")
            if not name:
                return {"error": "name is required"}
            return await sgs.delete_skill(db, name, deleted_by=owner_id)

        elif action == "scan":
            base_dir = params.get("base_dir", "data/skills")
            return await sgs.scan_file_skills_to_registry(db, base_dir=base_dir, created_by=owner_id)

        elif action == "usage":
            skill_name = params.get("name")
            days = params.get("days", 7)
            stats = await sgs.get_skill_usage_stats(db, skill_name=skill_name, days=days)
            return {"stats": stats}

        elif action == "provenance":
            name = params.get("name", "")
            if not name:
                return {"error": "name is required"}
            trail = await sgs.get_skill_provenance(db, name)
            return {"provenance": trail, "skill_name": name}

        elif action == "pending_approvals":
            approvals = await sgs.list_pending_skill_approvals(db)
            return {"pending_approvals": approvals, "total": len(approvals)}

        elif action == "approve":
            approval_id = params.get("approval_id")
            if not approval_id:
                return {"error": "approval_id is required"}
            return await sgs.resolve_skill_approval(
                db, approval_id=int(approval_id),
                decision="approved", decided_by=owner_id,
                reason=params.get("reason"),
            )

        elif action == "reject":
            approval_id = params.get("approval_id")
            if not approval_id:
                return {"error": "approval_id is required"}
            return await sgs.resolve_skill_approval(
                db, approval_id=int(approval_id),
                decision="rejected", decided_by=owner_id,
                reason=params.get("reason"),
            )

        else:
            return {"error": f"Unknown action: {action}"}


# ── Profile 2.0 capabilities ──

async def _cap_get_role_profiles(params: dict, caller: str) -> dict:
    """List role profiles."""
    from app.database import AsyncSessionLocal

    from ..services.profile_service import list_role_profiles
    async with AsyncSessionLocal() as db:
        profiles = await list_role_profiles(db)
        return {"profiles": profiles}


async def _cap_get_role_profile(params: dict, caller: str) -> dict:
    """Get a specific role profile."""
    from app.database import AsyncSessionLocal

    from ..services.profile_service import get_role_profile
    role_key = params.get("role_key", "")
    if not role_key:
        return {"error": "role_key is required"}
    async with AsyncSessionLocal() as db:
        profile = await get_role_profile(db, role_key)
        if not profile:
            return {"error": f"Role profile '{role_key}' not found"}
        return profile


async def _cap_upsert_role_profile(params: dict, caller: str) -> dict:
    """Create or update a role profile."""
    from app.database import AsyncSessionLocal

    from ..services.profile_service import upsert_role_profile
    role_key = params.get("role_key", "")
    if not role_key:
        return {"error": "role_key is required"}
    async with AsyncSessionLocal() as db:
        owner_id = resolve_caller_user_id(caller)
        return await upsert_role_profile(db, role_key, params, updated_by=owner_id)


async def _cap_get_enterprise_profile(params: dict, caller: str) -> dict:
    """Get the enterprise profile."""
    from app.database import AsyncSessionLocal

    from ..services.profile_service import get_enterprise_profile
    async with AsyncSessionLocal() as db:
        profile = await get_enterprise_profile(db)
        if not profile:
            return {"error": "Enterprise profile not configured"}
        return profile


async def _cap_upsert_enterprise_profile(params: dict, caller: str) -> dict:
    """Create or update the enterprise profile."""
    from app.database import AsyncSessionLocal

    from ..services.profile_service import upsert_enterprise_profile
    async with AsyncSessionLocal() as db:
        owner_id = resolve_caller_user_id(caller)
        return await upsert_enterprise_profile(db, params, updated_by=owner_id)


async def _cap_list_market_profiles(params: dict, caller: str) -> dict:
    """List market/product/brand/competitor profiles."""
    from app.database import AsyncSessionLocal

    from ..services.profile_service import list_market_profiles
    profile_type = params.get("profile_type")
    async with AsyncSessionLocal() as db:
        profiles = await list_market_profiles(db, profile_type=profile_type)
        return {"profiles": profiles}


async def _cap_upsert_market_profile(params: dict, caller: str) -> dict:
    """Create or update a market/product/brand/competitor profile."""
    from app.database import AsyncSessionLocal

    from ..services.profile_service import upsert_market_profile
    profile_type = params.get("profile_type", "")
    key = params.get("key", "")
    if not profile_type or not key:
        return {"error": "profile_type and key are required"}
    async with AsyncSessionLocal() as db:
        owner_id = resolve_caller_user_id(caller)
        return await upsert_market_profile(db, profile_type, key, params, updated_by=owner_id)


async def _cap_record_profile_signal(params: dict, caller: str) -> dict:
    """Record a low-confidence profile signal for later analysis."""
    from app.database import AsyncSessionLocal

    from ..services.profile_service import record_signal
    signal_type = params.get("signal_type", "")
    signal_data = params.get("signal_data", {})
    if not signal_type:
        return {"error": "signal_type is required"}
    owner_id = resolve_caller_user_id(caller)
    async with AsyncSessionLocal() as db:
        return await record_signal(
            db, owner_id=owner_id,
            signal_type=signal_type,
            signal_data=signal_data,
            target_profile_type=params.get("target_profile_type", "user"),
            confidence=params.get("confidence", 0.0),
            source=params.get("source", "auto"),
            conversation_id=params.get("conversation_id"),
        )


async def _cap_list_profile_signals(params: dict, caller: str) -> dict:
    """List profile signals (with optional filters)."""
    from app.database import AsyncSessionLocal

    from ..services.profile_service import list_signals
    owner_id = resolve_caller_user_id(caller)
    async with AsyncSessionLocal() as db:
        signals = await list_signals(
            db, owner_id=owner_id,
            signal_type=params.get("signal_type"),
            applied=params.get("applied"),
        )
        return {"signals": signals}


# ── Trajectory capabilities ──

async def _cap_record_trajectory(params: dict, caller: str) -> dict:
    """Record a trajectory turn for research analysis."""
    from app.database import AsyncSessionLocal

    from ..services.trajectory_service import record_turn
    owner_id = resolve_caller_user_id(caller)
    async with AsyncSessionLocal() as db:
        return await record_turn(
            db,
            conversation_id=params.get("conversation_id", 0),
            owner_id=owner_id,
            session_id=params.get("session_id", ""),
            turn_index=params.get("turn_index", 0),
            user_input=params.get("user_input", ""),
            tool_calls=params.get("tool_calls"),
            tool_results=params.get("tool_results"),
            assistant_response=params.get("assistant_response"),
            user_correction=params.get("user_correction"),
            failure_recovery=params.get("failure_recovery"),
            thinking_level=params.get("thinking_level"),
            profile_signals=params.get("profile_signals"),
            error_occurred=params.get("error_occurred", False),
            duration_ms=params.get("duration_ms"),
            token_count=params.get("token_count"),
        )


async def _cap_list_trajectories(params: dict, caller: str) -> dict:
    """List trajectory records for analysis."""
    from app.database import AsyncSessionLocal

    from ..services.trajectory_service import list_trajectories
    owner_id = resolve_caller_user_id(caller)
    async with AsyncSessionLocal() as db:
        records = await list_trajectories(
            db, owner_id=owner_id,
            conversation_id=params.get("conversation_id"),
            session_id=params.get("session_id"),
        )
        return {"records": records}


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
    description="读取当前用户的个人画像。个人画像包含用户的语气偏好、禁忌话题、关注领域和习惯。",
    brief="读取我的画像",
    parameters={},
    min_role="viewer",
)
register_capability(
    "agent", "update_my_profile", _cap_update_my_profile,
    description="更新当前用户的个人画像（仅能改自己的）。owner 固定为当前用户。",
    brief="更新我的画像",
    parameters={
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
    },
    min_role="viewer",
)
register_capability(
    "agent", "spawn_subagent", _cap_spawn_subagent,
    description="委托子 Agent 执行任务（支持单任务/批量/工具白名单/写保护/执行轨迹/Gate 校验）。默认只给读类工具，写类需设置 write_enabled=True。",
    brief="委托子Agent执行任务",
    parameters={
        "task": {"type": "string", "description": "单任务描述"},
        "tasks": {"type": "array", "items": {"type": "object"}, "description": "批量任务列表"},
        "tools": {"type": "array", "items": {"type": "string"}, "description": "限定可用工具列表"},
        "context": {"type": "string", "description": "参考上下文"},
        "write_enabled": {"type": "boolean", "description": "是否允许写操作"},
        "track_trajectory": {"type": "boolean", "description": "是否记录执行轨迹"},
        "max_rounds": {"type": "integer", "description": "最大工具轮数"},
        "gates": {"type": "boolean", "description": "是否启用质量门控校验"},
        "gate_retry": {"type": "integer", "description": "门控失败最多重试次数，默认 1"},
    },
    min_role="viewer",
)

# ── V2.0 new capabilities ──

register_capability(
    "agent", "skill_manage", _cap_skill_manage,
    description="管理技能：列表、创建、更新、删除、扫描、使用统计、来源追溯和审批。",
    brief="管理技能",
    parameters={
        "action": {"type": "string", "description": "list/get/create/update/delete/scan/usage/provenance/pending-approvals/approve/reject"},
        "name": {"type": "string", "description": "技能名称"},
        "description": {"type": "string", "description": "技能描述"},
        "body": {"type": "string", "description": "技能内容"},
        "allowed_tools": {"type": "array", "items": {"type": "string"}, "description": "允许的工具列表"},
        "scope": {"type": "string", "description": "作用域"},
    },
    min_role="admin",
)
register_capability(
    "agent", "get_role_profiles", _cap_get_role_profiles,
    description="列出所有岗位/角色画像。",
    brief="列出岗位画像",
    parameters={},
    min_role="viewer",
)
register_capability(
    "agent", "get_role_profile", _cap_get_role_profile,
    description="获取指定岗位/角色的详细画像。",
    brief="查看岗位画像",
    parameters={"role_key": {"type": "string", "description": "岗位标识"}},
    min_role="viewer",
)
register_capability(
    "agent", "upsert_role_profile", _cap_upsert_role_profile,
    description="创建或更新岗位/角色画像（管理员权限）。",
    brief="管理岗位画像",
    parameters={"role_key": {"type": "string"}, "role_name": {"type": "string"},
                 "tone": {"type": "string"}, "taboos": {"type": "array", "items": {"type": "string"}},
                 "focus_areas": {"type": "array", "items": {"type": "string"}},
                 "allowed_tools": {"type": "array", "items": {"type": "string"}}},
    min_role="admin",
)
register_capability(
    "agent", "get_enterprise_profile", _cap_get_enterprise_profile,
    description="获取企业级画像：语气、业务规则、沟通风格等。",
    brief="查看企业画像",
    parameters={},
    min_role="viewer",
)
register_capability(
    "agent", "upsert_enterprise_profile", _cap_upsert_enterprise_profile,
    description="创建或更新企业级画像（管理员权限）。",
    brief="管理企业画像",
    parameters={"enterprise_name": {"type": "string"}, "tone": {"type": "string"},
                 "business_rules": {"type": "array", "items": {"type": "string"}},
                 "communication_style": {"type": "string"}},
    min_role="admin",
)
register_capability(
    "agent", "list_market_profiles", _cap_list_market_profiles,
    description="列出市场/产品/品牌/竞品画像。",
    brief="列出市场画像",
    parameters={"profile_type": {"type": "string", "description": "可选过滤：product/brand/competitor"}},
    min_role="viewer",
)
register_capability(
    "agent", "upsert_market_profile", _cap_upsert_market_profile,
    description="创建或更新市场/产品/品牌/竞品画像（管理员权限）。",
    brief="管理市场画像",
    parameters={"profile_type": {"type": "string"}, "key": {"type": "string"},
                 "name": {"type": "string"}, "attributes": {"type": "object"},
                 "tags": {"type": "array", "items": {"type": "string"}}},
    min_role="admin",
)
register_capability(
    "agent", "record_profile_signal", _cap_record_profile_signal,
    description="记录一条低置信度的画像信号。低置信信号不会直接修改正式画像。",
    brief="记录画像信号",
    parameters={"signal_type": {"type": "string"}, "signal_data": {"type": "object"},
                 "confidence": {"type": "number"}, "target_profile_type": {"type": "string"}},
    min_role="viewer",
)
register_capability(
    "agent", "list_profile_signals", _cap_list_profile_signals,
    description="列出画像信号池中的信号。",
    brief="查看画像信号",
    parameters={"signal_type": {"type": "string", "description": "可选过滤"},
                 "applied": {"type": "boolean", "description": "可选过滤是否已应用"}},
    min_role="viewer",
)
register_capability(
    "agent", "record_trajectory", _cap_record_trajectory,
    description="记录一次执行轨迹（用于研究分析）。",
    brief="记录执行轨迹",
    parameters={"session_id": {"type": "string"}, "conversation_id": {"type": "integer"},
                 "user_input": {"type": "string"}},
    min_role="viewer",
)
register_capability(
    "agent", "list_trajectories", _cap_list_trajectories,
    description="列出执行轨迹记录（管理员权限）。",
    brief="查看执行轨迹",
    parameters={"conversation_id": {"type": "integer", "description": "可选过滤"},
                 "session_id": {"type": "string", "description": "可选过滤"}},
    min_role="admin",
)
