"""Profile 2.0 service: multi-dimensional profiles with signal pool.

Supports role profiles, enterprise profiles, market/product/brand
profiles, and a low-confidence signal pool that feeds into the
profile evolution pipeline.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import and_, desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models import (
    AgentEnterpriseProfile,
    AgentMarketProfile,
    AgentProfileSignal,
    AgentRoleProfile,
    AgentUserProfile,
)

logger = logging.getLogger("v2.agent").getChild("services.profile_service")

# ── Role Profile ────────────────────────────────────────────────


async def get_role_profile(db: AsyncSession, role_key: str) -> dict | None:
    r = await db.execute(
        select(AgentRoleProfile).where(
            AgentRoleProfile.role_key == role_key,
            AgentRoleProfile.enabled == True,
        )
    )
    item = r.scalar_one_or_none()
    if not item:
        return None
    return {
        "id": item.id,
        "role_key": item.role_key,
        "role_name": item.role_name,
        "description": item.description,
        "tone": item.tone,
        "taboos": item.taboos,
        "focus_areas": item.focus_areas,
        "habits": item.habits,
        "allowed_tools": item.allowed_tools,
        "priority": item.priority,
        "enabled": item.enabled,
        "version": item.version,
    }


async def list_role_profiles(db: AsyncSession) -> list[dict]:
    r = await db.execute(
        select(AgentRoleProfile)
        .order_by(AgentRoleProfile.priority.desc(), AgentRoleProfile.role_key)
    )
    return [_role_to_dict(item) for item in r.scalars().all()]


async def upsert_role_profile(db: AsyncSession, role_key: str, data: dict, updated_by: int | None = None) -> dict:
    r = await db.execute(
        select(AgentRoleProfile).where(AgentRoleProfile.role_key == role_key)
    )
    item = r.scalar_one_or_none()
    if item:
        for key in ("role_name", "description", "tone", "taboos", "focus_areas", "habits", "allowed_tools", "priority", "enabled"):
            if key in data:
                setattr(item, key, data[key])
        item.version = (item.version or 1) + 1
        item.updated_by = updated_by
    else:
        item = AgentRoleProfile(
            role_key=role_key,
            role_name=data.get("role_name", ""),
            description=data.get("description", ""),
            tone=data.get("tone"),
            taboos=data.get("taboos", []),
            focus_areas=data.get("focus_areas", []),
            habits=data.get("habits", []),
            allowed_tools=data.get("allowed_tools", []),
            priority=data.get("priority", 0),
            enabled=data.get("enabled", True),
            updated_by=updated_by,
        )
        db.add(item)
    await db.commit()
    await db.refresh(item)
    return _role_to_dict(item)


async def delete_role_profile(db: AsyncSession, role_key: str) -> dict:
    r = await db.execute(
        select(AgentRoleProfile).where(AgentRoleProfile.role_key == role_key)
    )
    item = r.scalar_one_or_none()
    if not item:
        return {"error": f"Role profile '{role_key}' not found"}
    await db.delete(item)
    await db.commit()
    return {"deleted": True, "role_key": role_key}


def _role_to_dict(item: AgentRoleProfile) -> dict:
    return {
        "id": item.id,
        "role_key": item.role_key,
        "role_name": item.role_name,
        "description": item.description,
        "tone": item.tone,
        "taboos": item.taboos,
        "focus_areas": item.focus_areas,
        "habits": item.habits,
        "allowed_tools": item.allowed_tools,
        "priority": item.priority,
        "enabled": item.enabled,
        "version": item.version,
        "updated_by": item.updated_by,
        "created_at": item.created_at.isoformat() if item.created_at else None,
    }


# ── Enterprise Profile ──────────────────────────────────────────


async def get_enterprise_profile(db: AsyncSession, enterprise_key: str = "default") -> dict | None:
    r = await db.execute(
        select(AgentEnterpriseProfile).where(AgentEnterpriseProfile.enterprise_key == enterprise_key)
    )
    item = r.scalar_one_or_none()
    if not item:
        return None
    return {
        "id": item.id,
        "enterprise_key": item.enterprise_key,
        "enterprise_name": item.enterprise_name,
        "description": item.description,
        "tone": item.tone,
        "taboos": item.taboos,
        "focus_areas": item.focus_areas,
        "business_rules": item.business_rules,
        "communication_style": item.communication_style,
        "version": item.version,
    }


async def upsert_enterprise_profile(db: AsyncSession, data: dict, updated_by: int | None = None) -> dict:
    key = data.get("enterprise_key", "default")
    r = await db.execute(
        select(AgentEnterpriseProfile).where(AgentEnterpriseProfile.enterprise_key == key)
    )
    item = r.scalar_one_or_none()
    if item:
        for field in ("enterprise_name", "description", "tone", "taboos", "focus_areas", "business_rules", "communication_style"):
            if field in data:
                setattr(item, field, data[field])
        item.version = (item.version or 1) + 1
        item.updated_by = updated_by
    else:
        item = AgentEnterpriseProfile(
            enterprise_key=key,
            enterprise_name=data.get("enterprise_name", ""),
            description=data.get("description", ""),
            tone=data.get("tone"),
            taboos=data.get("taboos", []),
            focus_areas=data.get("focus_areas", []),
            business_rules=data.get("business_rules", []),
            communication_style=data.get("communication_style"),
            updated_by=updated_by,
        )
        db.add(item)
    await db.commit()
    await db.refresh(item)
    return {
        "id": item.id,
        "enterprise_key": item.enterprise_key,
        "enterprise_name": item.enterprise_name,
        "description": item.description,
        "tone": item.tone,
        "taboos": item.taboos,
        "focus_areas": item.focus_areas,
        "business_rules": item.business_rules,
        "communication_style": item.communication_style,
        "version": item.version,
    }


# ── Market Profile (Product / Brand / Competitor) ───────────────


async def list_market_profiles(db: AsyncSession, profile_type: str | None = None) -> list[dict]:
    q = select(AgentMarketProfile).order_by(AgentMarketProfile.priority.desc())
    if profile_type:
        q = q.where(AgentMarketProfile.profile_type == profile_type)
    r = await db.execute(q)
    return [_market_to_dict(item) for item in r.scalars().all()]


async def get_market_profile(db: AsyncSession, profile_type: str, key: str) -> dict | None:
    r = await db.execute(
        select(AgentMarketProfile).where(
            AgentMarketProfile.profile_type == profile_type,
            AgentMarketProfile.key == key,
        )
    )
    item = r.scalar_one_or_none()
    if not item:
        return None
    return _market_to_dict(item)


async def upsert_market_profile(db: AsyncSession, profile_type: str, key: str, data: dict, updated_by: int | None = None) -> dict:
    r = await db.execute(
        select(AgentMarketProfile).where(
            AgentMarketProfile.profile_type == profile_type,
            AgentMarketProfile.key == key,
        )
    )
    item = r.scalar_one_or_none()
    if item:
        for field in ("name", "description", "attributes", "tags", "enabled", "priority"):
            if field in data:
                setattr(item, field, data[field])
        item.version = (item.version or 1) + 1
        item.updated_by = updated_by
    else:
        item = AgentMarketProfile(
            profile_type=profile_type,
            key=key,
            name=data.get("name", ""),
            description=data.get("description", ""),
            attributes=data.get("attributes", {}),
            tags=data.get("tags", []),
            enabled=data.get("enabled", True),
            priority=data.get("priority", 0),
            updated_by=updated_by,
        )
        db.add(item)
    await db.commit()
    await db.refresh(item)
    return _market_to_dict(item)


async def delete_market_profile(db: AsyncSession, profile_type: str, key: str) -> dict:
    r = await db.execute(
        select(AgentMarketProfile).where(
            AgentMarketProfile.profile_type == profile_type,
            AgentMarketProfile.key == key,
        )
    )
    item = r.scalar_one_or_none()
    if not item:
        return {"error": f"Market profile '{profile_type}/{key}' not found"}
    await db.delete(item)
    await db.commit()
    return {"deleted": True, "profile_type": profile_type, "key": key}


def _market_to_dict(item: AgentMarketProfile) -> dict:
    return {
        "id": item.id,
        "profile_type": item.profile_type,
        "key": item.key,
        "name": item.name,
        "description": item.description,
        "attributes": item.attributes,
        "tags": item.tags,
        "enabled": item.enabled,
        "priority": item.priority,
        "version": item.version,
        "updated_by": item.updated_by,
        "created_at": item.created_at.isoformat() if item.created_at else None,
    }


# ── Profile Signal Pool ─────────────────────────────────────────


async def record_signal(
    db: AsyncSession,
    owner_id: int,
    signal_type: str,
    signal_data: dict,
    target_profile_type: str = "user",
    confidence: float = 0.0,
    source: str = "auto",
    conversation_id: int | None = None,
) -> dict:
    """Record a low-confidence profile signal."""
    signal = AgentProfileSignal(
        owner_id=owner_id,
        signal_type=signal_type,
        target_profile_type=target_profile_type,
        signal_data=signal_data,
        confidence=min(max(confidence, 0.0), 1.0),
        source=source,
        conversation_id=conversation_id,
        applied=False,
    )
    db.add(signal)
    await db.commit()
    await db.refresh(signal)
    return {
        "id": signal.id,
        "signal_type": signal_type,
        "confidence": signal.confidence,
        "applied": False,
    }


async def list_signals(
    db: AsyncSession,
    owner_id: int | None = None,
    signal_type: str | None = None,
    applied: bool | None = None,
    limit: int = 50,
) -> list[dict]:
    q = select(AgentProfileSignal).order_by(AgentProfileSignal.created_at.desc()).limit(limit)
    if owner_id is not None:
        q = q.where(AgentProfileSignal.owner_id == owner_id)
    if signal_type:
        q = q.where(AgentProfileSignal.signal_type == signal_type)
    if applied is not None:
        q = q.where(AgentProfileSignal.applied == applied)
    r = await db.execute(q)
    return [
        {
            "id": s.id,
            "owner_id": s.owner_id,
            "signal_type": s.signal_type,
            "target_profile_type": s.target_profile_type,
            "signal_data": s.signal_data,
            "confidence": s.confidence,
            "source": s.source,
            "conversation_id": s.conversation_id,
            "applied": s.applied,
            "applied_at": s.applied_at.isoformat() if s.applied_at else None,
            "created_at": s.created_at.isoformat() if s.created_at else None,
        }
        for s in r.scalars().all()
    ]


async def apply_signals(db: AsyncSession, owner_id: int, signal_ids: list[int]) -> dict:
    """Mark signals as applied (e.g. after they've been incorporated into profiles)."""
    r = await db.execute(
        select(AgentProfileSignal).where(
            AgentProfileSignal.id.in_(signal_ids),
            AgentProfileSignal.owner_id == owner_id,
        )
    )
    now = datetime.now(timezone.utc)
    count = 0
    for signal in r.scalars().all():
        signal.applied = True
        signal.applied_at = now
        count += 1
    await db.commit()
    return {"applied": count}


# ── Profile Injection for Engine ────────────────────────────────


async def build_profile_injections(
    db: AsyncSession,
    owner_id: int,
    role_key: str | None = None,
    max_chars: int = 2000,
) -> str:
    """Build a compact profile injection string for engine context.

    Combines user profile, role profile (if available), and enterprise
    profile into a single formatted block. Respects max_chars to avoid
    context bloat.
    """
    parts: list[str] = []

    # User profile
    try:
        from .conversation_service import get_active_user_profile
        user_profile = await get_active_user_profile(db, owner_id)
        if user_profile:
            tone = user_profile.get("tone", "")
            taboos = user_profile.get("taboos", [])
            focus = user_profile.get("focus", [])
            habits = user_profile.get("habits", [])
            user_lines = []
            if tone:
                user_lines.append(f"语气：{tone}")
            if taboos:
                user_lines.append(f"禁忌话题：{', '.join(taboos[:5])}")
            if focus:
                user_lines.append(f"关注领域：{', '.join(focus[:5])}")
            if habits:
                user_lines.append(f"习惯：{', '.join(habits[:5])}")
            if user_lines:
                parts.append("【用户画像】\n" + "\n".join(user_lines))
    except Exception as e:
        logger.debug("User profile injection failed: %s", e)

    # Role profile
    if role_key:
        try:
            role = await get_role_profile(db, role_key)
            if role and role.get("tone"):
                parts.append(f"【角色：{role['role_name']}】\n语气：{role['tone']}")
        except Exception as e:
            logger.debug("Role profile injection failed: %s", e)

    # Enterprise profile
    try:
        ent = await get_enterprise_profile(db)
        if ent:
            ent_lines = []
            if ent.get("tone"):
                ent_lines.append(f"语气：{ent['tone']}")
            if ent.get("communication_style"):
                ent_lines.append(f"沟通风格：{ent['communication_style']}")
            if ent.get("business_rules"):
                rules = ent["business_rules"]
                if isinstance(rules, list) and rules:
                    ent_lines.append(f"业务规则：{'；'.join(rules[:3])}")
            if ent.get("focus_areas"):
                areas = ent["focus_areas"]
                if isinstance(areas, list) and areas:
                    ent_lines.append(f"关注领域：{'、'.join(areas[:3])}")
            if ent_lines:
                parts.append("【企业上下文】\n" + "\n".join(ent_lines))
    except Exception as e:
        logger.debug("Enterprise profile injection failed: %s", e)

    injection = "\n\n".join(parts)
    if len(injection) > max_chars:
        injection = injection[:max_chars] + "\n...（画像已截断）"
    return injection
