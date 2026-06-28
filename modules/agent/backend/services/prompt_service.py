import logging

from app.core.exceptions import ConflictError, NotFound, PermissionDenied
from sqlalchemy import desc, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models import AgentPrompt
from ..prompt_seeds import PROMPT_SCOPE_SYSTEM, PROMPT_SCOPE_USER

logger = logging.getLogger("v2.agent").getChild("prompt_service")


SYSTEM_OWNER_ID: int | None = None


def _prompt_to_dict(prompt: AgentPrompt) -> dict:
    return {
        "id": prompt.id,
        "owner_id": prompt.owner_id,
        "key": prompt.key,
        "title": prompt.title,
        "category": prompt.category,
        "content": prompt.content,
        "scope": prompt.scope,
        "is_read_only": prompt.is_read_only,
        "is_active": prompt.is_active,
        "status": prompt.status,
        "version": prompt.version,
        "created_at": prompt.created_at.isoformat() if prompt.created_at else None,
        "updated_at": prompt.updated_at.isoformat() if prompt.updated_at else None,
    }


def _is_system_prompt(prompt: AgentPrompt) -> bool:
    return prompt.scope == PROMPT_SCOPE_SYSTEM or bool(prompt.is_read_only)


def _ensure_user_can_mutate(prompt: AgentPrompt, owner_id: int, is_admin: bool = False) -> None:
    if _is_system_prompt(prompt):
        raise PermissionDenied("System prompt is read-only")
    if prompt.owner_id != owner_id:
        raise NotFound(f"Prompt '{prompt.id}' not found")
    if not is_admin and prompt.owner_id != owner_id:
        raise PermissionDenied("Cannot mutate another user's prompt")


async def list_prompts(
    db: AsyncSession,
    owner_id: int,
    category: str | None = None,
    include_system: bool = True,
) -> list[dict]:
    stmt = select(AgentPrompt).where(
        or_(AgentPrompt.owner_id == owner_id, AgentPrompt.scope == PROMPT_SCOPE_SYSTEM)
        if include_system
        else AgentPrompt.owner_id == owner_id
    ).order_by(desc(AgentPrompt.scope), desc(AgentPrompt.id))
    if category:
        stmt = stmt.where(AgentPrompt.category == category)
    result = await db.execute(stmt)
    return [_prompt_to_dict(item) for item in result.scalars().all()]


async def get_prompt(db: AsyncSession, owner_id: int, prompt_id: int) -> dict:
    prompt = await db.get(AgentPrompt, prompt_id)
    if not prompt:
        raise NotFound(f"Prompt '{prompt_id}' not found")
    if prompt.scope != PROMPT_SCOPE_SYSTEM and prompt.owner_id != owner_id:
        raise NotFound(f"Prompt '{prompt_id}' not found")
    return _prompt_to_dict(prompt)


async def create_prompt(db: AsyncSession, owner_id: int, data: dict) -> dict:
    scope = data.get("scope") or PROMPT_SCOPE_USER
    if scope == PROMPT_SCOPE_SYSTEM or data.get("is_read_only"):
        raise PermissionDenied("System prompts can only be created by module seed")
    key = (data.get("key") or "").strip()
    existing = await db.execute(
        select(AgentPrompt).where(
            AgentPrompt.owner_id == owner_id,
            AgentPrompt.key == key,
            AgentPrompt.title == data["title"],
            AgentPrompt.category == data["category"],
        )
    )
    if existing.scalar_one_or_none():
        raise ConflictError(f"Prompt '{data['title']}' already exists")
    prompt = AgentPrompt(
        owner_id=owner_id,
        key=key,
        title=data["title"],
        category=data["category"],
        content=data["content"],
        scope=PROMPT_SCOPE_USER,
        is_read_only=False,
        is_active=data.get("is_active", True),
        status=data.get("status", "draft"),
        version=1,
    )
    db.add(prompt)
    await db.commit()
    await db.refresh(prompt)
    return _prompt_to_dict(prompt)


async def update_prompt(
    db: AsyncSession,
    owner_id: int,
    prompt_id: int,
    data: dict,
    is_admin: bool = False,
) -> dict:
    prompt = await db.get(AgentPrompt, prompt_id)
    if not prompt:
        raise NotFound(f"Prompt '{prompt_id}' not found")
    _ensure_user_can_mutate(prompt, owner_id, is_admin=is_admin)
    if any(key in data for key in ("scope", "is_read_only")):
        raise PermissionDenied("Prompt ownership fields cannot be changed")
    if "key" in data and data["key"] is not None:
        prompt.key = str(data["key"]).strip()
    if "title" in data and data["title"] and data["title"] != prompt.title:
        existing = await db.execute(
            select(AgentPrompt).where(
                AgentPrompt.owner_id == owner_id,
                AgentPrompt.title == data["title"],
                AgentPrompt.category == data.get("category", prompt.category),
                AgentPrompt.id != prompt.id,
            )
        )
        if existing.scalar_one_or_none():
            raise ConflictError(f"Prompt '{data['title']}' already exists")
        prompt.title = data["title"]
    if "category" in data and data["category"]:
        prompt.category = data["category"]
    if "content" in data and data["content"] is not None:
        prompt.content = data["content"]
        prompt.version = (prompt.version or 1) + 1
    if "is_active" in data and data["is_active"] is not None:
        prompt.is_active = data["is_active"]
    if "status" in data and data["status"]:
        prompt.status = data["status"]
    await db.commit()
    await db.refresh(prompt)
    return _prompt_to_dict(prompt)


async def delete_prompt(db: AsyncSession, owner_id: int, prompt_id: int) -> dict:
    prompt = await db.get(AgentPrompt, prompt_id)
    if not prompt:
        raise NotFound(f"Prompt '{prompt_id}' not found")
    _ensure_user_can_mutate(prompt, owner_id)
    await db.delete(prompt)
    await db.commit()
    return {"ok": True}
