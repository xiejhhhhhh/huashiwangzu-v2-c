from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.knowledge import DisambigCandidate, Entity, EntityAlias


def entity_item(entity: Entity, aliases: list[EntityAlias] | None = None) -> dict:
    active_aliases = [a for a in aliases or [] if a.alias_type != "disabled"]
    return {
        "词典ID": entity.id, "标准名": entity.standard_name,
        "实体类型": entity.entity_type, "描述": None,
        "状态": entity.confirm_status, "别名列表": [a.alias for a in active_aliases],
        "创建人ID": None,
        "创建时间": entity.created_at.isoformat() if entity.created_at else None,
        "更新时间": entity.updated_at.isoformat() if entity.updated_at else None,
    }


def alias_item(alias: EntityAlias) -> dict:
    return {
        "别名ID": alias.id, "词典ID": alias.entity_id,
        "别名名称": alias.alias, "状态": alias.alias_type,
        "创建时间": alias.created_at.isoformat() if alias.created_at else None,
    }


async def load_alias_map(db: AsyncSession, entity_ids: list[int]) -> dict[int, list[EntityAlias]]:
    if not entity_ids:
        return {}
    rows = (await db.execute(select(EntityAlias).where(EntityAlias.entity_id.in_(entity_ids)))).scalars().all()
    result: dict[int, list[EntityAlias]] = {}
    for alias in rows:
        result.setdefault(alias.entity_id, []).append(alias)
    return result


async def load_entities(db: AsyncSession, entity_ids: set[int]) -> dict[int, Entity]:
    if not entity_ids:
        return {}
    rows = (await db.execute(select(Entity).where(Entity.id.in_(entity_ids)))).scalars().all()
    return {entity.id: entity for entity in rows}


def page_info(data: dict) -> dict:
    page_size = data["pageSize"]
    total_pages = (data["total"] + page_size - 1) // page_size if page_size else 0
    return {"当前页": data["page"], "每页条数": page_size, "总数": data["total"], "总页数": total_pages}


def disambig_item(item: DisambigCandidate, entities: dict[int, Entity]) -> dict:
    first = entities.get(item.entity_a_id)
    second = entities.get(item.entity_b_id)
    candidates = [{"词典ID": e.id, "标准名": e.standard_name, "上下文提示": ""} for e in [first, second] if e]
    names = [entity.standard_name for entity in [first, second] if entity]
    return {
        "歧义ID": item.id, "歧义关键词": " / ".join(names) or f"歧义 {item.id}",
        "候选实体列表": candidates,
        "相关词典ID列表": [item.entity_a_id, item.entity_b_id],
        "处理状态": item.review_status,
        "创建时间": item.created_at.isoformat() if item.created_at else None,
        "更新时间": item.updated_at.isoformat() if item.updated_at else None,
    }
