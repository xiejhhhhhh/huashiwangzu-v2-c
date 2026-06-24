import logging
from sqlalchemy import select, desc
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ConflictError, NotFound

from ..models import AgentPrompt

logger = logging.getLogger("v2.agent").getChild("prompt_service")


def _prompt_to_dict(prompt: AgentPrompt) -> dict:
    return {
        "id": prompt.id,
        "owner_id": prompt.owner_id,
        "title": prompt.title,
        "category": prompt.category,
        "content": prompt.content,
        "is_active": prompt.is_active,
        "status": prompt.status,
        "created_at": prompt.created_at.isoformat() if prompt.created_at else None,
        "updated_at": prompt.updated_at.isoformat() if prompt.updated_at else None,
    }


async def list_prompts(db: AsyncSession, owner_id: int, category: str | None = None) -> list[dict]:
    stmt = select(AgentPrompt).where(AgentPrompt.owner_id == owner_id).order_by(desc(AgentPrompt.id))
    if category:
        stmt = stmt.where(AgentPrompt.category == category)
    result = await db.execute(stmt)
    return [_prompt_to_dict(item) for item in result.scalars().all()]


async def get_prompt(db: AsyncSession, owner_id: int, prompt_id: int) -> dict:
    prompt = await db.get(AgentPrompt, prompt_id)
    if not prompt or prompt.owner_id != owner_id:
        raise NotFound(f"Prompt '{prompt_id}' not found")
    return _prompt_to_dict(prompt)


async def create_prompt(db: AsyncSession, owner_id: int, data: dict) -> dict:
    existing = await db.execute(
        select(AgentPrompt).where(
            AgentPrompt.owner_id == owner_id,
            AgentPrompt.title == data["title"],
            AgentPrompt.category == data["category"],
        )
    )
    if existing.scalar_one_or_none():
        raise ConflictError(f"Prompt '{data['title']}' already exists")
    prompt = AgentPrompt(
        owner_id=owner_id,
        title=data["title"],
        category=data["category"],
        content=data["content"],
        is_active=data.get("is_active", True),
        status=data.get("status", "draft"),
    )
    db.add(prompt)
    await db.commit()
    await db.refresh(prompt)
    return _prompt_to_dict(prompt)


async def update_prompt(db: AsyncSession, owner_id: int, prompt_id: int, data: dict) -> dict:
    prompt = await db.get(AgentPrompt, prompt_id)
    if not prompt or prompt.owner_id != owner_id:
        raise NotFound(f"Prompt '{prompt_id}' not found")
    if "title" in data and data["title"] and data["title"] != prompt.title:
        existing = await db.execute(
            select(AgentPrompt).where(
                AgentPrompt.owner_id == owner_id,
                AgentPrompt.title == data["title"],
                AgentPrompt.category == data.get("category", prompt.category),
            )
        )
        if existing.scalar_one_or_none():
            raise ConflictError(f"Prompt '{data['title']}' already exists")
        prompt.title = data["title"]
    if "category" in data:
        prompt.category = data["category"]
    if "content" in data:
        prompt.content = data["content"]
    if "is_active" in data and data["is_active"] is not None:
        prompt.is_active = data["is_active"]
    if "status" in data and data["status"]:
        prompt.status = data["status"]
    await db.commit()
    await db.refresh(prompt)
    return _prompt_to_dict(prompt)


async def delete_prompt(db: AsyncSession, owner_id: int, prompt_id: int) -> dict:
    prompt = await db.get(AgentPrompt, prompt_id)
    if not prompt or prompt.owner_id != owner_id:
        raise NotFound(f"Prompt '{prompt_id}' not found")
    await db.delete(prompt)
    await db.commit()
    return {"ok": True}
