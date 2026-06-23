"""Sensitive action policy enforcement for agent tool calls.

判定规则（多因素）：
1. 能力本身的 min_role（admin 级能力自动敏感）
2. Agent 配置的 sensitive_action_policy（allow/confirm/block）
3. 能力是否在硬编码的敏感名单中

确认流：confirm 策略下，工具不直接执行 → 插入 agent_approval_queue →
返回等待确认 → admin 同意/拒绝后继续/取消。
"""
import json
import logging
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger("v2.agent").getChild("action_policy")

# Sensitive tool name patterns (module__action or prefix match)
# module__action exact match, or module__* wildcard
SENSITIVE_ACTION_PATTERNS: list[str] = [
    "desktop-tools__write_file",
    "desktop-tools__delete_file",
    "desktop-tools__move_file",
    "desktop-tools__copy_file",
    "terminal-tools__execute",
    "agent__update_system_prompt",
    "agent__update_enterprise_prompt",
    "agent__spawn_subagent",
    "im__send",
    "im__notify",
    "scheduler__create",
    "scheduler__update",
    "scheduler__delete",
    "file-manager__*",
    "git__*",
    "admin__*",
]

# Actions that are only for admins (min_role=admin from capability registry)
# These are always treated as sensitive regardless of the pattern list
ADMIN_ACTIONS: set[str] = {
    "agent__update_system_prompt",
    "agent__update_enterprise_prompt",
}


def _match_sensitive(tool_name: str) -> bool:
    """Check if a tool name matches any sensitive pattern.

    Exact match (module__action) or prefix+wildcard (module__*).
    """
    for pattern in SENSITIVE_ACTION_PATTERNS:
        if pattern == tool_name:
            return True
        if pattern.endswith("__*"):
            prefix = pattern[:-3]  # remove __*
            if tool_name.startswith(prefix + "__"):
                return True
    return False


async def check_action_allowed(
    db: AsyncSession,
    tool_name: str,
    agent_code: str,
    user_id: int,
    conversation_id: int | None = None,
) -> dict:
    """Check whether a tool action is allowed under the agent's policy.

    Returns:
        {"allowed": True} — proceed normally
        {"allowed": False, "action": "block", "reason": "..."} — rejected
        {"allowed": False, "action": "confirm", "approval_id": int,
         "tool_name": str, "tool_args": dict} — needs admin approval
    """
    # 1. Check if the action is sensitive
    is_sensitive = _match_sensitive(tool_name) or tool_name in ADMIN_ACTIONS

    # 2. If not sensitive, always allow
    if not is_sensitive:
        return {"allowed": True}

    # 3. Read the agent's sensitive_action_policy from agent_configs
    from .models import AgentConfig
    r = await db.execute(
        select(AgentConfig).where(AgentConfig.agent_code == agent_code)
    )
    config = r.scalar_one_or_none()
    if not config:
        # No specific config for this agent → default to confirm for sensitive
        policy = "confirm"
    else:
        policy = config.sensitive_action_policy or "confirm"

    # 4. Apply policy
    if policy == "allow":
        return {"allowed": True}
    elif policy == "block":
        return {
            "allowed": False,
            "action": "block",
            "reason": f"Action '{tool_name}' is blocked by admin policy (agent: {agent_code})",
        }
    elif policy == "confirm":
        # Insert into approval queue
        from .models import ApprovalQueue
        approval = ApprovalQueue(
            agent_code=agent_code,
            tool_name=tool_name,
            tool_args="",
            status="pending",
            requested_by=user_id,
            conversation_id=conversation_id,
        )
        db.add(approval)
        await db.commit()
        await db.refresh(approval)
        logger.info(
            "Sensitive action requires approval: tool=%s agent=%s user=%d approval_id=%d",
            tool_name, agent_code, user_id, approval.id,
        )
        return {
            "allowed": False,
            "action": "confirm",
            "approval_id": approval.id,
            "tool_name": tool_name,
        }
    else:
        # Unknown policy → fallback to allow
        logger.warning("Unknown sensitive_action_policy '%s' for agent '%s', allowing", policy, agent_code)
        return {"allowed": True}


async def resolve_approval(
    db: AsyncSession,
    approval_id: int,
    decision: str,
    decided_by: int,
    reason: str | None = None,
) -> dict:
    """Admin resolves a pending approval.

    decision: "approved" or "rejected"
    Returns the updated approval record.
    """
    from datetime import datetime, timezone
    from .models import ApprovalQueue
    r = await db.execute(
        select(ApprovalQueue).where(ApprovalQueue.id == approval_id)
    )
    approval = r.scalar_one_or_none()
    if not approval:
        return {"error": f"Approval {approval_id} not found"}
    if approval.status != "pending":
        return {"error": f"Approval {approval_id} already {approval.status}"}
    approval.status = decision
    approval.decided_by = decided_by
    approval.reason = reason
    approval.decided_at = datetime.now(timezone.utc)
    await db.commit()
    logger.info(
        "Approval %d %s by user %d: tool=%s reason=%s",
        approval_id, decision, decided_by, approval.tool_name, reason or "",
    )
    return {
        "id": approval.id,
        "agent_code": approval.agent_code,
        "tool_name": approval.tool_name,
        "status": approval.status,
        "reason": approval.reason,
        "decided_by": approval.decided_by,
    }


async def list_pending_approvals(db: AsyncSession) -> list[dict]:
    """List all pending approvals for admin review."""
    from .models import ApprovalQueue
    r = await db.execute(
        select(ApprovalQueue)
        .where(ApprovalQueue.status == "pending")
        .order_by(ApprovalQueue.id.desc())
        .limit(50)
    )
    items = r.scalars().all()
    return [
        {
            "id": a.id,
            "agent_code": a.agent_code,
            "tool_name": a.tool_name,
            "tool_args": a.tool_args,
            "status": a.status,
            "requested_by": a.requested_by,
            "conversation_id": a.conversation_id,
            "created_at": a.created_at.isoformat() if a.created_at else None,
        }
        for a in items
    ]
