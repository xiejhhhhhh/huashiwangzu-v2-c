"""Codemap 模块表初始化：幂等建表，防重复。
使用原生 SQL，因为 codemap 模块在路由加载后才初始化数据库连接，
而 Base.metadata.create_all 只在框架启动时执行一次。"""
import logging

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger("v2.codemap").getChild("init_db")

_CREATE_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS codemap_feedback (
    id SERIAL PRIMARY KEY,
    path VARCHAR(1024) NOT NULL,
    query_type VARCHAR(32) NOT NULL,
    codemap_said TEXT DEFAULT '',
    actual TEXT DEFAULT '',
    reason TEXT DEFAULT '',
    agent_id VARCHAR(128) DEFAULT '',
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);
"""

_CREATE_METRICS_SQL = """
CREATE TABLE IF NOT EXISTS codemap_metrics (
    id INTEGER PRIMARY KEY DEFAULT 1 CHECK (id = 1),
    query_count INTEGER NOT NULL DEFAULT 0
);
"""

_SEED_METRICS_SQL = """
INSERT INTO codemap_metrics (id, query_count)
SELECT 1, 0
WHERE NOT EXISTS (SELECT 1 FROM codemap_metrics WHERE id = 1);
"""


async def ensure_codemap_tables(db: AsyncSession) -> None:
    """Ensure codemap_feedback and codemap_metrics tables exist, one SQL at a time.
    asyncpg does not support multiple statements in a single execute().
    Raises on failure — the caller (_ensure_tables_once) depends on the exception
    to skip setting _tables_ensured, so the next request retries the table creation."""
    try:
        await db.execute(text(_CREATE_TABLE_SQL))
        await db.execute(text("CREATE INDEX IF NOT EXISTS idx_codemap_feedback_path ON codemap_feedback(path)"))
        await db.execute(text(_CREATE_METRICS_SQL))
        await db.execute(text(_SEED_METRICS_SQL))
        await db.commit()
        logger.info("codemap tables ensured")
    except Exception as exc:
        await db.rollback()
        logger.warning("Failed to ensure codemap tables: %s", exc)
        raise
