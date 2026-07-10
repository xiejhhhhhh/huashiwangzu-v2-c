"""Outbound approval policy for agent tool calls.

审批只用于 Agent 代表用户对外发送、上传、发布或发言的场景。
本地可回退操作（文件生成/替换、Office 产物、本地命令、数据库有版本写入）
默认放行，由日志、版本和节点回顾兜底。
"""
import json
import logging
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger("v2.agent").getChild("action_policy")

_APPROVAL_ARGS_MAX_CHARS = 12000
_APPROVAL_ARG_STRING_MAX_CHARS = 2000
_APPROVAL_ARG_LIST_MAX_ITEMS = 50
_APPROVAL_ARG_DICT_MAX_ITEMS = 100
_APPROVAL_ARG_MAX_DEPTH = 8
_REDACTED_VALUE = "[REDACTED]"
_SENSITIVE_ARG_KEY_PARTS = (
    "api_key",
    "apikey",
    "authorization",
    "cookie",
    "jwt",
    "password",
    "passwd",
    "private_key",
    "refresh_token",
    "secret",
    "token",
)

# Actions that represent the user outside the local, reversible workspace.
# Exact module__action match or module__* wildcard.  Local file/Office/terminal
# operations are intentionally absent: those are recoverable in this product.
OUTBOUND_APPROVAL_PATTERNS: list[str] = [
    "im__send",
    "im__notify",
    "email__send",
    "mail__send",
    "wechat__send",
    "wechat__publish",
    "douyin__publish",
    "douyin__upload",
    "webhook__send",
    "external__*",
    "payment__*",
]

# The current product has no irreversible local tool exposed to Agent.  Keep the
# set for future hard-block policy without blocking recoverable local work now.
SYSTEM_HARD_BLOCKED_ACTIONS: set[str] = set()

# Admin-only configuration is still protected, but it is not normal user-file
# workflow approval.  It follows the same queue only when an Agent tries it.
ADMIN_ACTIONS: set[str] = {
    "agent__update_system_prompt",
    "agent__update_enterprise_prompt",
}


def _match_sensitive(tool_name: str) -> bool:
    """Check if a tool name requires approval.

    Exact match (module__action) or prefix+wildcard (module__*).
    """
    for pattern in OUTBOUND_APPROVAL_PATTERNS:
        if pattern == tool_name:
            return True
        if pattern.endswith("__*"):
            prefix = pattern[:-3]  # remove __*
            if tool_name.startswith(prefix + "__"):
                return True
    return False


def classify_side_effect_level(tool_name: str) -> str:
    """Return the workflow side-effect class for a tool name."""
    normalized = (tool_name or "").lower()
    if _match_sensitive(tool_name):
        return "outbound"
    if tool_name in ADMIN_ACTIONS:
        return "admin_config"
    write_terms = (
        "create",
        "delete",
        "exec",
        "generate",
        "move",
        "publish",
        "replace",
        "send",
        "update",
        "upload",
        "write",
    )
    if any(term in normalized for term in write_terms):
        return "workspace_write"
    return "readonly"


def _is_sensitive_arg_key(key: str) -> bool:
    normalized = key.lower().replace("-", "_")
    return any(part in normalized for part in _SENSITIVE_ARG_KEY_PARTS)


def _truncate_text(value: str, max_chars: int = _APPROVAL_ARG_STRING_MAX_CHARS) -> str:
    if len(value) <= max_chars:
        return value
    omitted = len(value) - max_chars
    return f"{value[:max_chars]}...(truncated {omitted} chars)"


def _sanitize_tool_arg_value(value: Any, key: str | None = None, depth: int = 0) -> Any:
    if key and _is_sensitive_arg_key(key):
        return _REDACTED_VALUE
    if depth > _APPROVAL_ARG_MAX_DEPTH:
        return "...(truncated: max depth)"
    if isinstance(value, dict):
        sanitized: dict[str, Any] = {}
        items = list(value.items())
        for raw_key, raw_value in items[:_APPROVAL_ARG_DICT_MAX_ITEMS]:
            item_key = str(raw_key)
            sanitized[item_key] = _sanitize_tool_arg_value(raw_value, item_key, depth + 1)
        if len(items) > _APPROVAL_ARG_DICT_MAX_ITEMS:
            sanitized["..."] = f"truncated {len(items) - _APPROVAL_ARG_DICT_MAX_ITEMS} keys"
        return sanitized
    if isinstance(value, (list, tuple, set)):
        items = list(value)
        sanitized_items = [
            _sanitize_tool_arg_value(item, None, depth + 1)
            for item in items[:_APPROVAL_ARG_LIST_MAX_ITEMS]
        ]
        if len(items) > _APPROVAL_ARG_LIST_MAX_ITEMS:
            sanitized_items.append(f"...(truncated {len(items) - _APPROVAL_ARG_LIST_MAX_ITEMS} items)")
        return sanitized_items
    if isinstance(value, str):
        return _truncate_text(value)
    if isinstance(value, bytes):
        return f"<bytes {len(value)}>"
    if value is None or isinstance(value, (bool, int, float)):
        return value
    return _truncate_text(str(value))


def _serialize_tool_args_for_approval(tool_args: Any | None) -> str:
    """Serialize tool args for human approval review without storing raw secrets."""
    sanitized = _sanitize_tool_arg_value(tool_args if tool_args is not None else {})
    try:
        serialized = json.dumps(sanitized, ensure_ascii=False, default=str, sort_keys=True)
    except Exception as exc:
        fallback = {
            "_serialization_error": str(exc),
            "_preview": _truncate_text(str(tool_args), max_chars=1000),
        }
        serialized = json.dumps(fallback, ensure_ascii=False, sort_keys=True)
    if len(serialized) <= _APPROVAL_ARGS_MAX_CHARS:
        return serialized
    preview = {
        "_truncated": True,
        "_original_chars": len(serialized),
        "_preview_json": serialized[:_APPROVAL_ARGS_MAX_CHARS],
    }
    return json.dumps(preview, ensure_ascii=False, sort_keys=True)


async def check_action_allowed(
    db: AsyncSession,
    tool_name: str,
    agent_code: str,
    user_id: int,
    conversation_id: int | None = None,
    tool_args: Any | None = None,
    workflow_run_id: int | None = None,
    workflow_step_id: int | None = None,
    workflow_tool_call_id: int | None = None,
    workflow_resume_target: dict | None = None,
) -> dict:
    """Check whether a tool action is allowed under the agent's policy.

    Returns:
        {"allowed": True} — proceed normally
        {"allowed": False, "action": "block", "reason": "..."} — rejected
        {"allowed": False, "action": "confirm", "approval_id": int,
         "tool_name": str, "tool_args": str} — needs admin approval
    """
    # System principal hard blocks are reserved for future irreversible tools.
    if user_id == 0 and tool_name in SYSTEM_HARD_BLOCKED_ACTIONS:
        return {
            "allowed": False,
            "action": "block",
            "reason": f"Action '{tool_name}' is hard blocked for system principal (no user context)",
        }

    # 1. Check if the action requires approval. Local recoverable actions do not.
    is_sensitive = _match_sensitive(tool_name) or tool_name in ADMIN_ACTIONS

    # 2. If not sensitive, always allow
    if not is_sensitive:
        return {"allowed": True}

    # 3. Read the agent's sensitive_action_policy from agent_configs
    from ..models import AgentConfig
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
        if workflow_run_id and workflow_tool_call_id:
            from . import workflow_service

            approval = await workflow_service.request_approval(
                db,
                run_id=workflow_run_id,
                tool_call_id=workflow_tool_call_id,
                requested_by=user_id,
                agent_code=agent_code,
                reason=f"Sensitive action requires confirmation: {tool_name}",
                request_type="tool_call",
                risk_level="sensitive",
                decision_scope="single_call",
                resume_target=workflow_resume_target or {
                    "workflow_run_id": workflow_run_id,
                    "workflow_step_id": workflow_step_id,
                    "tool_call_id": workflow_tool_call_id,
                },
            )
            logger.info(
                "Sensitive workflow action requires approval: tool=%s agent=%s user=%d approval_id=%d",
                tool_name, agent_code, user_id, approval.id,
            )
            return {
                "allowed": False,
                "action": "confirm",
                "approval_id": approval.id,
                "tool_name": tool_name,
                "tool_args": approval.tool_args,
                "payload_hash": approval.payload_hash,
                "resume_target": approval.resume_target,
            }
        # Insert into approval queue
        from ..models import ApprovalQueue
        approval = ApprovalQueue(
            agent_code=agent_code,
            tool_name=tool_name,
            tool_args=_serialize_tool_args_for_approval(tool_args),
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
            "tool_args": approval.tool_args,
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
    payload_hash: str | None = None,
) -> dict:
    """Admin resolves a pending approval.

    decision: "approved" or "rejected"
    Returns the updated approval record.
    """
    from datetime import datetime, timezone

    from ..models import ApprovalQueue
    r = await db.execute(
        select(ApprovalQueue).where(ApprovalQueue.id == approval_id)
    )
    approval = r.scalar_one_or_none()
    if not approval:
        return {"error": f"Approval {approval_id} not found"}
    if approval.status != "pending":
        return {"error": f"Approval {approval_id} already {approval.status}"}
    if approval.workflow_run_id:
        from . import workflow_service

        return await workflow_service.resolve_approval(
            db,
            approval_id=approval_id,
            decision=decision,
            decided_by=decided_by,
            reason=reason,
            payload_hash=payload_hash,
        )
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
    from ..models import ApprovalQueue
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
            "workflow_run_id": a.workflow_run_id,
            "workflow_step_id": a.workflow_step_id,
            "tool_call_id": a.tool_call_id,
            "request_type": a.request_type,
            "risk_level": a.risk_level,
            "decision_scope": a.decision_scope,
            "payload_hash": a.payload_hash,
            "resume_target": a.resume_target,
            "expires_at": a.expires_at.isoformat() if a.expires_at else None,
            "created_at": a.created_at.isoformat() if a.created_at else None,
        }
        for a in items
    ]
