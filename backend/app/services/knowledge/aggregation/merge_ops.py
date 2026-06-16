from __future__ import annotations

from datetime import datetime

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.knowledge import (
    Entity, EntityAlias, EntityMerge,
    GraphNode, GraphEdge, SemanticRole,
)


async def execute_merge(db: AsyncSession, from_eid: int, to_eid: int, confidence: float) -> EntityMerge:
    from_entity = await db.get(Entity, from_eid)
    to_entity = await db.get(Entity, to_eid)
    if not from_entity or not to_entity:
        raise ValueError(f"Entity not found: from={from_eid}, to={to_eid}")

    reverse_map = {
        "from_entity_id": from_eid,
        "to_entity_id": to_eid,
        "from_standard_name": from_entity.standard_name,
        "to_standard_name": to_entity.standard_name,
        "merged_at": datetime.utcnow().isoformat(),
    }

    existing_alias_values = await db.execute(
        select(EntityAlias.alias).where(EntityAlias.entity_id == to_eid)
    )
    existing_alias_set = {r[0] for r in existing_alias_values.all()}

    from_aliases = await db.execute(
        select(EntityAlias).where(EntityAlias.entity_id == from_eid)
    )
    for alias in from_aliases.scalars().all():
        if alias.alias not in existing_alias_set:
            alias.entity_id = to_eid
            existing_alias_set.add(alias.alias)

    if from_entity.standard_name not in existing_alias_set:
        db.add(EntityAlias(
            entity_id=to_eid,
            alias=from_entity.standard_name,
            alias_type="legacy",
        ))

    from_entity.confirm_status = "rejected"

    from_node = await db.execute(select(GraphNode).where(GraphNode.entity_id == from_eid))
    from_node_obj = from_node.scalar_one_or_none()
    to_node = await db.execute(select(GraphNode).where(GraphNode.entity_id == to_eid))
    to_node_obj = to_node.scalar_one_or_none()

    if from_node_obj:
        if to_node_obj:
            to_node_obj.occurrence_count = (
                (to_node_obj.occurrence_count or 0) + (from_node_obj.occurrence_count or 0)
            )
            await db.execute(
                update(GraphEdge)
                .where(GraphEdge.from_node_id == from_node_obj.id)
                .values(from_node_id=to_node_obj.id)
            )
            await db.execute(
                update(GraphEdge)
                .where(GraphEdge.to_node_id == from_node_obj.id)
                .values(to_node_id=to_node_obj.id)
            )
            await db.delete(from_node_obj)
        else:
            from_node_obj.entity_id = to_eid

    roles = await db.execute(
        select(SemanticRole).where(
            SemanticRole.role_value.ilike(f"%{from_entity.standard_name}%")
        )
    )
    from_name = from_entity.standard_name
    to_name = to_entity.standard_name
    if from_name == to_name:
        pass
    elif len(from_name) <= 2 and len(to_name) >= 6 and from_name in to_name:
        pass
    else:
        for role in roles.scalars().all():
            role.role_value = role.role_value.replace(from_name, to_name)

    to_entity.occurrence_count = (to_entity.occurrence_count or 0) + (from_entity.occurrence_count or 0)
    merge_record = EntityMerge(
        from_entity_id=from_eid,
        to_entity_id=to_eid,
        reason=f"auto-merge confidence={confidence}",
        reverse_map=reverse_map,
        merged_at=datetime.utcnow().isoformat(),
    )
    db.add(merge_record)
    return merge_record


async def rollback_merge(db: AsyncSession, merge_record_id: int) -> bool:
    merge_record = await db.get(EntityMerge, merge_record_id)
    if not merge_record:
        raise ValueError(f"Merge record not found: {merge_record_id}")

    reverse_map = merge_record.reverse_map or {}
    from_eid = reverse_map.get("from_entity_id")
    to_eid = reverse_map.get("to_entity_id")
    if not from_eid or not to_eid:
        raise ValueError("Invalid reverse_map, cannot rollback")

    to_entity = await db.get(Entity, to_eid)
    from_entity = await db.get(Entity, from_eid)
    if not from_entity:
        from_entity = Entity(
            id=from_eid,
            standard_name=reverse_map.get("from_standard_name", "unknown"),
            confirm_status="pending",
        )
        db.add(from_entity)

    aliases_to_restore = await db.execute(
        select(EntityAlias).where(
            EntityAlias.entity_id == to_eid,
            EntityAlias.alias_type == "legacy",
            EntityAlias.alias == reverse_map.get("from_standard_name"),
        )
    )
    for alias in aliases_to_restore.scalars().all():
        alias.entity_id = from_eid

    if to_entity and from_entity:
        to_entity.occurrence_count = max(
            0, (to_entity.occurrence_count or 0) - (from_entity.occurrence_count or 0)
        )
        from_entity.confirm_status = "confirmed"

    await db.delete(merge_record)
    await db.commit()
    return True
