import logging
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger("migrate_v1.helpers")


async def migrate_entities(db: AsyncSession, entities: list[Any]) -> dict[Any, Any]:
    id_map: dict[Any, Any] = {}
    for item in entities:
        try:
            name = item["标准名"]
            existing = await db.execute(
                text(
                    "SELECT id FROM knowledge_entities "
                    "WHERE standard_name = :name"
                ),
                {"name": name},
            )
            row = existing.scalar_one_or_none()
            if row:
                id_map[item["词典ID"]] = row
                continue
            result = await db.execute(
                text(
                    """
                    INSERT INTO knowledge_entities
                    (standard_name, entity_type, confirm_status, occurrence_count)
                    VALUES (:name, :etype, :status, 1)
                    RETURNING id
                    """
                ),
                {
                    "name": name,
                    "etype": item["实体类型"],
                    "status": "confirmed" if item.get("状态") == "正常" else "pending",
                },
            )
            id_map[item["词典ID"]] = result.scalar_one()
        except Exception as exc:
            logger.warning("Entity insert failed for %s: %s", item.get("标准名"), exc)
    await db.commit()
    return id_map


async def migrate_aliases(
    db: AsyncSession,
    id_map: dict[Any, Any],
    aliases: list[Any],
) -> int:
    count = 0
    for item in aliases:
        entity_id = id_map.get(item["词典ID"])
        if not entity_id:
            continue
        try:
            await db.execute(
                text(
                    """
                    INSERT INTO knowledge_entity_aliases
                    (entity_id, alias, alias_type)
                    VALUES (:entity_id, :alias, 'alias')
                    ON CONFLICT DO NOTHING
                    """
                ),
                {"entity_id": entity_id, "alias": item["别名名称"]},
            )
            count += 1
        except Exception as exc:
            logger.warning("Alias insert failed: %s", exc)
    await db.commit()
    return count


async def migrate_labels(
    db: AsyncSession,
    id_map: dict[Any, Any],
    labels: list[Any],
) -> int:
    count = 0
    for item in labels:
        entity_id = id_map.get(item["词典ID"])
        if not entity_id:
            continue
        try:
            await db.execute(
                text(
                    """
                    INSERT INTO knowledge_labels
                    (target_type, target_id, label, label_category, passed_admission)
                    VALUES ('entity', :entity_id, :label, COALESCE(:ltype, 'auto'), true)
                    ON CONFLICT DO NOTHING
                    """
                ),
                {"entity_id": entity_id, "label": item["标签名"], "ltype": item.get("实体类型")},
            )
            count += 1
        except Exception as exc:
            logger.warning("Label insert failed: %s", exc)
    await db.commit()
    return count
