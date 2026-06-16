#!/usr/bin/env python3
"""
从 V1 (huashi_v1_raw PG) 向 V2 (华世王镞_v2) 搬运实体/标签/图谱数据。

用法:
    cd backend && source .venv/bin/activate
    PYTHONPATH=. python3 scripts/maintenance/migrate_v1_entities.py
"""

import asyncio
import logging
import os

import asyncpg
from app.config import get_settings
from app.database import AsyncSessionLocal
from scripts.maintenance.v1_entity_migration_helpers import migrate_aliases
from scripts.maintenance.v1_entity_migration_helpers import migrate_entities
from scripts.maintenance.v1_entity_migration_helpers import migrate_labels
from scripts.maintenance.v1_graph_migration_helpers import migrate_edges
from scripts.maintenance.v1_graph_migration_helpers import migrate_nodes

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s %(message)s",
)
logger = logging.getLogger("migrate_v1")

SOURCE_DB_NAME = os.getenv("V1_RAW_DB_NAME", "huashi_v1_raw")


def source_dsn() -> str:
    settings = get_settings()
    password = os.getenv("V1_RAW_DB_PASSWORD", settings.DB_PASSWORD)
    return (
        f"postgresql://{settings.DB_USER}:{password}"
        f"@{settings.DB_HOST}:{settings.DB_PORT}/{SOURCE_DB_NAME}"
    )


async def load_source_data() -> tuple[list, list, list, list, list]:
    src_pool = await asyncpg.create_pool(source_dsn(), min_size=1, max_size=2)
    logger.info("Connected to %s", SOURCE_DB_NAME)
    try:
        async with src_pool.acquire() as conn:
            return (
                await conn.fetch('SELECT * FROM "知识_实体词典"'),
                await conn.fetch('SELECT * FROM "知识_实体别名"'),
                await conn.fetch('SELECT * FROM "知识_实体标签"'),
                await conn.fetch('SELECT * FROM "知识_图谱节点"'),
                await conn.fetch('SELECT * FROM "知识_图谱边"'),
            )
    finally:
        await src_pool.close()


async def migrate() -> None:
    entities, aliases, labels, nodes, edges = await load_source_data()
    logger.info(
        "Fetched: entities=%d, aliases=%d, labels=%d, nodes=%d, edges=%d",
        len(entities), len(aliases), len(labels), len(nodes), len(edges),
    )

    async with AsyncSessionLocal() as db:
        id_map = await migrate_entities(db, entities)
        logger.info("entities: %d rows, id_map: %d", len(entities), len(id_map))
        alias_count = await migrate_aliases(db, id_map, aliases)
        logger.info("aliases: %d rows", alias_count)
        label_count = await migrate_labels(db, id_map, labels)
        logger.info("labels: %d rows", label_count)
        node_map = await migrate_nodes(db, id_map, entities, nodes)
        logger.info("graph_nodes: %d rows", len(node_map))
        edge_count = await migrate_edges(db, node_map, edges)
        logger.info("graph_edges: %d rows", edge_count)

    logger.info("Migration complete!")


if __name__ == "__main__":
    asyncio.run(migrate())
