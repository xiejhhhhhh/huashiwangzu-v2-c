"""Entity service — write entities, aliases, and merges with controlled access."""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.models.knowledge.entity import Entity, EntityAlias
from app.services.knowledge.dictionary.quality import passes_entity_gate
from app.services.knowledge.dictionary.seed import (
    resolve_brand, is_known_entity, get_brand_aliases,
)


async def find_entity(
    db: AsyncSession, standard_name: str
) -> Entity | None:
    result = await db.execute(
        select(Entity).where(Entity.standard_name == standard_name)
    )
    return result.scalar_one_or_none()


async def find_entity_by_alias(
    db: AsyncSession, alias: str
) -> Entity | None:
    """Look up entity through alias table."""
    result = await db.execute(
        select(EntityAlias).where(EntityAlias.alias == alias)
    )
    ea = result.scalar_one_or_none()
    if ea:
        result2 = await db.execute(select(Entity).where(Entity.id == ea.entity_id))
        return result2.scalar_one_or_none()
    return None


async def create_entity(
    db: AsyncSession,
    standard_name: str,
    entity_type: str,
    confirm_status: str = "confirmed",
) -> Entity:
    entity = Entity(
        standard_name=standard_name,
        entity_type=entity_type,
        confirm_status=confirm_status,
        pinyin="",
        occurrence_count=1,
    )
    db.add(entity)
    await db.flush()

    brand_aliases = get_brand_aliases().get(standard_name, [])
    for alias in brand_aliases:
        existing = await find_entity_by_alias(db, alias)
        if not existing:
            db.add(EntityAlias(
                entity_id=entity.id, alias=alias, alias_type="synonym"
            ))

    await db.flush()
    return entity


async def upsert_entity(
    db: AsyncSession,
    standard_name: str,
    entity_type: str,
    confirm_status: str = "confirmed",
) -> Entity:
    resolved = resolve_brand(standard_name)
    effective_name = resolved or standard_name

    existing = await find_entity(db, effective_name)
    if existing:
        existing.occurrence_count = (existing.occurrence_count or 0) + 1
        if resolved and resolved != standard_name:
            await add_alias(db, existing.id, standard_name, "synonym")
        return existing

    return await create_entity(db, effective_name, entity_type, confirm_status)


async def add_alias(
    db: AsyncSession,
    entity_id: int,
    alias: str,
    alias_type: str = "synonym",
) -> EntityAlias | None:
    result = await db.execute(
        select(EntityAlias).where(
            EntityAlias.entity_id == entity_id,
            EntityAlias.alias == alias,
        )
    )
    if result.scalar_one_or_none():
        return None
    ea = EntityAlias(entity_id=entity_id, alias=alias, alias_type=alias_type)
    db.add(ea)
    await db.flush()
    return ea


async def create_entity_from_candidate(
    db: AsyncSession,
    standard_name: str,
    entity_type: str,
) -> Entity:
    if not passes_entity_gate(standard_name):
        raise ValueError(f"Entity '{standard_name}' failed quality gate")
    return await upsert_entity(db, standard_name, entity_type)
