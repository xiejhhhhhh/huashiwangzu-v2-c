"""Skill lifecycle governance service.

Provides CRUD, approval gate, provenance tracking, usage statistics,
and minimal scan v1 for skills managed through the agent module.

Key design:
  - Review fork proposals cannot directly create/modify skills;
    they must go through approval gate (status = pending_approval).
  - Skills from file scan are imported into agent_skill_registry
    on startup with approval_status = 'approved' (file is source of truth).
  - DB-authored skills start at approval_status = 'pending_approval'
    until an admin approves them via the approval API.
  - Provenance records every create/update/delete event.
  - Usage records every invocation (success/fail, duration).
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import TYPE_CHECKING

from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models import (
    SkillApproval,
    SkillProvenance,
    SkillRegistryItem,
    SkillUsage,
)

if TYPE_CHECKING:
    from ..engine.skills_loader import SkillDef

logger = logging.getLogger("v2.agent").getChild("services.skill_governance")


# ── CRUD ─────────────────────────────────────────────────────────────────


async def list_skills(
    db: AsyncSession,
    scope: str | None = None,
    enabled_only: bool = False,
    limit: int = 100,
) -> list[dict]:
    """List registered skills with governance metadata."""
    q = select(SkillRegistryItem).order_by(SkillRegistryItem.priority.desc(), SkillRegistryItem.name).limit(limit)
    if scope:
        q = q.where(SkillRegistryItem.scope == scope)
    if enabled_only:
        q = q.where(SkillRegistryItem.enabled.is_(True))
    r = await db.execute(q)
    return [
        {
            "id": item.id,
            "name": item.name,
            "description": item.description,
            "source": item.source,
            "scope": item.scope,
            "priority": item.priority,
            "enabled": item.enabled,
            "approval_status": item.approval_status,
            "allowed_tools": item.allowed_tools,
            "paths": item.paths,
            "created_by": item.created_by,
            "created_at": item.created_at.isoformat() if item.created_at else None,
        }
        for item in r.scalars().all()
    ]


async def list_active_skill_defs(
    db: AsyncSession,
    current_path: str = "",
    limit: int = 1000,
) -> list["SkillDef"]:
    """Load the approved, enabled skills visible to the runtime prompt."""
    from ..engine.skills_loader import SkillDef, match_skills, resolve_skill_priority

    result = await db.execute(
        select(SkillRegistryItem)
        .where(
            SkillRegistryItem.enabled.is_(True),
            SkillRegistryItem.approval_status == "approved",
        )
        .order_by(SkillRegistryItem.priority.desc(), SkillRegistryItem.name)
        .limit(max(1, int(limit))),
    )
    skills = [
        SkillDef(
            name=item.name,
            description=item.description or "",
            allowed_tools=list(item.allowed_tools or []),
            paths=list(item.paths or []),
            body=item.body or "",
            enabled=bool(item.enabled),
            scope=item.scope or "global",
            priority=int(item.priority or 0),
        )
        for item in result.scalars().all()
    ]
    return match_skills(resolve_skill_priority(skills), current_path)


async def get_skill(db: AsyncSession, name: str) -> dict | None:
    """Get a single skill by name."""
    r = await db.execute(
        select(SkillRegistryItem).where(SkillRegistryItem.name == name)
    )
    item = r.scalar_one_or_none()
    if not item:
        return None
    return {
        "id": item.id,
        "name": item.name,
        "description": item.description,
        "source": item.source,
        "source_file": item.source_file,
        "body": item.body,
        "allowed_tools": item.allowed_tools,
        "paths": item.paths,
        "scope": item.scope,
        "priority": item.priority,
        "enabled": item.enabled,
        "approval_status": item.approval_status,
        "created_by": item.created_by,
        "updated_by": item.updated_by,
        "created_at": item.created_at.isoformat() if item.created_at else None,
    }


async def create_skill(
    db: AsyncSession,
    name: str,
    description: str = "",
    body: str = "",
    allowed_tools: list | None = None,
    paths: list | None = None,
    scope: str = "global",
    priority: int = 0,
    source: str = "manual",
    created_by: int | None = None,
) -> dict:
    """Create a new skill. Starts at pending_approval unless source=file_scan."""
    existing = await db.execute(
        select(SkillRegistryItem).where(SkillRegistryItem.name == name)
    )
    if existing.scalar_one_or_none():
        return {"error": f"Skill '{name}' already exists"}

    approval_status = "approved" if source == "file_scan" else "pending_approval"

    item = SkillRegistryItem(
        name=name,
        description=description,
        source=source,
        body=body,
        allowed_tools=allowed_tools or [],
        paths=paths or [],
        scope=scope,
        priority=priority,
        enabled=True,
        approval_status=approval_status,
        created_by=created_by,
        updated_by=created_by,
    )
    db.add(item)
    await db.commit()
    await db.refresh(item)

    await _record_provenance(db, name, "created", source, {"created_by": created_by}, created_by)

    logger.info("Skill created: %s (source=%s, approval=%s)", name, source, approval_status)
    return {"id": item.id, "name": item.name, "approval_status": item.approval_status}


async def update_skill(
    db: AsyncSession,
    name: str,
    updates: dict,
    updated_by: int | None = None,
    from_review: bool = False,
) -> dict:
    """Update a skill.  If from_review, sets approval_status to pending_approval."""
    r = await db.execute(
        select(SkillRegistryItem).where(SkillRegistryItem.name == name)
    )
    item = r.scalar_one_or_none()
    if not item:
        return {"error": f"Skill '{name}' not found"}

    prev_state = {
        "description": item.description,
        "body": item.body,
        "allowed_tools": item.allowed_tools,
        "paths": item.paths,
        "scope": item.scope,
        "priority": item.priority,
        "enabled": item.enabled,
    }

    for key in ("description", "body", "scope", "source"):
        if key in updates:
            setattr(item, key, updates[key])
    if "allowed_tools" in updates:
        item.allowed_tools = updates["allowed_tools"]
    if "paths" in updates:
        item.paths = updates["paths"]
    if "priority" in updates:
        item.priority = int(updates["priority"])
    if "enabled" in updates:
        item.enabled = bool(updates["enabled"])

    if from_review and item.approval_status == "approved":
        item.approval_status = "pending_approval"

    item.updated_by = updated_by
    await db.commit()

    await _record_provenance(
        db, name, "updated", "manual" if not from_review else "review_proposal",
        {"changes": updates, "prev": prev_state}, updated_by,
    )

    logger.info("Skill updated: %s (from_review=%s)", name, from_review)
    return {"id": item.id, "name": item.name, "approval_status": item.approval_status}


async def delete_skill(
    db: AsyncSession,
    name: str,
    deleted_by: int | None = None,
) -> dict:
    """Soft-delete a skill by setting enabled=False."""
    r = await db.execute(
        select(SkillRegistryItem).where(SkillRegistryItem.name == name)
    )
    item = r.scalar_one_or_none()
    if not item:
        return {"error": f"Skill '{name}' not found"}

    item.enabled = False
    item.updated_by = deleted_by
    await db.commit()

    await _record_provenance(db, name, "deleted", "manual", {}, deleted_by)
    logger.info("Skill deleted (soft): %s", name)
    return {"name": name, "enabled": False}


# ── Approval Gate ────────────────────────────────────────────────────────


async def list_pending_skill_approvals(db: AsyncSession, limit: int = 50) -> list[dict]:
    """List all pending skill approvals."""
    r = await db.execute(
        select(SkillApproval)
        .where(SkillApproval.status == "pending_approval")
        .order_by(desc(SkillApproval.created_at))
        .limit(limit)
    )
    return [
        {
            "id": a.id,
            "skill_name": a.skill_name,
            "operation": a.operation,
            "previous_state": a.previous_state,
            "requested_state": a.requested_state,
            "status": a.status,
            "requested_by": a.requested_by,
            "review_result_id": a.review_result_id,
            "reason": a.reason,
            "created_at": a.created_at.isoformat() if a.created_at else None,
        }
        for a in r.scalars().all()
    ]


async def resolve_skill_approval(
    db: AsyncSession,
    approval_id: int,
    decision: str,
    decided_by: int,
    reason: str | None = None,
) -> dict:
    """Approve or reject a skill approval request."""
    r = await db.execute(
        select(SkillApproval).where(SkillApproval.id == approval_id)
    )
    approval = r.scalar_one_or_none()
    if not approval:
        return {"error": f"Approval {approval_id} not found"}
    if approval.status != "pending_approval":
        return {"error": f"Approval {approval_id} is already {approval.status}"}

    approval.status = decision
    approval.decided_by = decided_by
    approval.decided_at = datetime.now(timezone.utc)
    approval.reason = reason
    await db.commit()

    # If approved and the skill is pending_approval, update skill record
    if decision == "approved":
        r2 = await db.execute(
            select(SkillRegistryItem).where(SkillRegistryItem.name == approval.skill_name)
        )
        skill = r2.scalar_one_or_none()
        if skill and skill.approval_status == "pending_approval":
            skill.approval_status = "approved"
            if approval.requested_state:
                for key, val in approval.requested_state.items():
                    if hasattr(skill, key):
                        setattr(skill, key, val)
            await db.commit()
            await _record_provenance(
                db, approval.skill_name, "approved", "admin",
                {"approval_id": approval_id, "decided_by": decided_by},
                decided_by,
            )

    logger.info("Skill approval %s: %s -> %s", approval_id, approval.skill_name, decision)
    return {"id": approval.id, "skill_name": approval.skill_name, "status": decision}


async def request_skill_approval(
    db: AsyncSession,
    skill_name: str,
    operation: str,
    previous_state: dict | None = None,
    requested_state: dict | None = None,
    requested_by: int | None = None,
    review_result_id: int | None = None,
) -> SkillApproval | None:
    """Create an approval request for a skill operation."""
    approval = SkillApproval(
        skill_name=skill_name,
        operation=operation,
        previous_state=previous_state,
        requested_state=requested_state,
        status="pending_approval",
        requested_by=requested_by or 0,
        review_result_id=review_result_id,
    )
    db.add(approval)
    await db.commit()
    await db.refresh(approval)
    return approval


# ── Usage Tracking ───────────────────────────────────────────────────────


async def record_skill_usage(
    db: AsyncSession,
    skill_name: str,
    success: bool,
    duration_ms: float = 0.0,
    conversation_id: int | None = None,
    owner_id: int | None = None,
    error_detail: str | None = None,
) -> None:
    """Record a skill invocation."""
    try:
        db.add(SkillUsage(
            skill_name=skill_name,
            conversation_id=conversation_id,
            owner_id=owner_id,
            success=success,
            duration_ms=round(duration_ms, 1),
            error_detail=error_detail,
        ))
        await db.commit()
    except Exception as exc:
        logger.warning("Failed to record skill usage: %s", exc)


async def get_skill_usage_stats(
    db: AsyncSession,
    skill_name: str | None = None,
    days: int = 7,
) -> list[dict]:
    """Aggregate usage stats per skill."""
    from sqlalchemy import text

    if skill_name:
        rows = await db.execute(text("""
            SELECT skill_name,
                   COUNT(*) AS total_calls,
                   SUM(CASE WHEN success THEN 1 ELSE 0 END) AS success_count,
                   ROUND(CAST(AVG(duration_ms) AS numeric), 1) AS avg_duration_ms,
                   COUNT(CASE WHEN NOT success THEN 1 END) AS error_count
            FROM agent_skill_usage
            WHERE skill_name = :sn AND created_at >= NOW() - INTERVAL '1 day' * :days_int
            GROUP BY skill_name
        """), {"sn": skill_name, "days_int": days})
    else:
        rows = await db.execute(text("""
            SELECT skill_name,
                   COUNT(*) AS total_calls,
                   SUM(CASE WHEN success THEN 1 ELSE 0 END) AS success_count,
                   ROUND(CAST(AVG(duration_ms) AS numeric), 1) AS avg_duration_ms,
                   COUNT(CASE WHEN NOT success THEN 1 END) AS error_count
            FROM agent_skill_usage
            WHERE created_at >= NOW() - INTERVAL '1 day' * :days_int
            GROUP BY skill_name
            ORDER BY total_calls DESC
        """), {"days_int": days})

    results = rows.fetchall() or []
    return [
        {
            "skill_name": r[0],
            "total_calls": r[1],
            "success_count": r[2],
            "avg_duration_ms": r[3],
            "error_count": r[4],
            "error_rate": round(r[4] / max(r[1], 1), 3),
        }
        for r in results
    ]


# ── Scan v1 ──────────────────────────────────────────────────────────────


async def scan_file_skills_to_registry(
    db: AsyncSession,
    base_dir: str = "data/skills",
    created_by: int | None = None,
) -> dict:
    """Synchronize Markdown skill files into the governed registry."""
    from ..engine.skills_loader import SkillsLoader, resolve_skill_priority

    loader = SkillsLoader(base_dir=base_dir)
    file_skills = loader.find_skills()
    file_skills = resolve_skill_priority(file_skills)

    imported = 0
    skipped = 0
    errors = 0

    for skill in file_skills:
        try:
            existing = await db.execute(
                select(SkillRegistryItem).where(SkillRegistryItem.name == skill.name)
            )
            item = existing.scalar_one_or_none()
            if item is not None:
                if item.source == "file_scan":
                    item.description = skill.description
                    item.body = skill.body
                    item.allowed_tools = skill.allowed_tools
                    item.paths = skill.paths
                    item.scope = skill.scope
                    item.priority = skill.priority
                    item.enabled = skill.enabled
                    item.approval_status = "approved"
                    await db.commit()
                skipped += 1
                continue

            await create_skill(
                db,
                name=skill.name,
                description=skill.description,
                body=skill.body,
                allowed_tools=skill.allowed_tools,
                paths=skill.paths,
                scope=skill.scope,
                priority=skill.priority,
                source="file_scan",
                created_by=created_by,
            )
            imported += 1
        except Exception as exc:
            logger.warning("Scan import failed for skill '%s': %s", skill.name, exc)
            errors += 1

    logger.info("Skill scan: imported=%d skipped=%d errors=%d", imported, skipped, errors)
    return {"imported": imported, "skipped": skipped, "errors": errors}


# ── Provenance ────────────────────────────────────────────────────────────


async def _record_provenance(
    db: AsyncSession,
    skill_name: str,
    event_type: str,
    source: str,
    detail: dict | None = None,
    actor_id: int | None = None,
) -> None:
    """Record a provenance event for a skill."""
    try:
        db.add(SkillProvenance(
            skill_name=skill_name,
            event_type=event_type,
            source=source,
            detail=detail or {},
            actor_id=actor_id,
        ))
        await db.commit()
    except Exception as exc:
        logger.warning("Failed to record provenance: %s", exc)


async def get_skill_provenance(
    db: AsyncSession,
    skill_name: str,
    limit: int = 50,
) -> list[dict]:
    """Get provenance trail for a skill."""
    r = await db.execute(
        select(SkillProvenance)
        .where(SkillProvenance.skill_name == skill_name)
        .order_by(desc(SkillProvenance.created_at))
        .limit(limit)
    )
    return [
        {
            "id": p.id,
            "skill_name": p.skill_name,
            "event_type": p.event_type,
            "source": p.source,
            "detail": p.detail,
            "actor_id": p.actor_id,
            "created_at": p.created_at.isoformat() if p.created_at else None,
        }
        for p in r.scalars().all()
    ]
