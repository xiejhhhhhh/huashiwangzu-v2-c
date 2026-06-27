"""知识库模块表初始化：确保知识库表在数据库中存在，支持无痛列补齐。"""
import logging
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession
from app.models.base import Base

logger = logging.getLogger("v2.knowledge").getChild("init_db")

# 知识库模块的所有表名
KB_TABLES = [
    "kb_catalogs", "kb_documents", "kb_chunks", "kb_page_fusions",
    "kb_raw_data", "kb_document_profiles", "kb_file_relations",
    "kb_entity_dictionary", "kb_entity_aliases", "kb_disambiguation",
    "kb_graph_nodes", "kb_graph_edges", "kb_chunk_entities",
    "kb_evidence", "kb_conclusion_evidence", "kb_entity_merge_log",
    "kb_governance_candidates",
]

# 关键索引语句（幂等，CREATE INDEX IF NOT EXISTS）
_INDEX_STATEMENTS = [
    "CREATE INDEX IF NOT EXISTS idx_kb_documents_owner ON kb_documents(owner_id) WHERE NOT deleted",
    "CREATE INDEX IF NOT EXISTS idx_kb_documents_catalog ON kb_documents(catalog_id) WHERE NOT deleted",
    "CREATE INDEX IF NOT EXISTS idx_kb_documents_status ON kb_documents(parse_status)",
    "CREATE INDEX IF NOT EXISTS idx_kb_chunks_doc ON kb_chunks(document_id)",
    "CREATE INDEX IF NOT EXISTS idx_kb_chunks_owner ON kb_chunks(owner_id)",
    "CREATE INDEX IF NOT EXISTS idx_kb_page_fusions_doc_page ON kb_page_fusions(document_id, page)",
    "CREATE INDEX IF NOT EXISTS idx_kb_entity_dict_owner ON kb_entity_dictionary(owner_id)",
    "CREATE INDEX IF NOT EXISTS idx_kb_graph_nodes_entity ON kb_graph_nodes(entity_id)",
    "CREATE INDEX IF NOT EXISTS idx_kb_graph_edges_source ON kb_graph_edges(source_node_id)",
    "CREATE INDEX IF NOT EXISTS idx_kb_graph_edges_target ON kb_graph_edges(target_node_id)",
    "CREATE INDEX IF NOT EXISTS idx_kb_evidence_entity ON kb_evidence(entity_id)",
    "CREATE INDEX IF NOT EXISTS idx_kb_chunk_entities_chunk ON kb_chunk_entities(chunk_id)",
    "CREATE INDEX IF NOT EXISTS idx_kb_chunk_entities_entity ON kb_chunk_entities(entity_id)",
    "CREATE INDEX IF NOT EXISTS idx_kb_governance_status ON kb_governance_candidates(audit_status)",
    "CREATE INDEX IF NOT EXISTS idx_kb_governance_owner ON kb_governance_candidates(owner_id)",
    "CREATE INDEX IF NOT EXISTS idx_kb_raw_data_doc_page_round ON kb_raw_data(document_id, page, round)",
    "CREATE INDEX IF NOT EXISTS idx_kb_raw_data_doc ON kb_raw_data(document_id)",
    "CREATE INDEX IF NOT EXISTS idx_kb_raw_data_owner ON kb_raw_data(owner_id)",
    "CREATE INDEX IF NOT EXISTS idx_kb_doc_profiles_doc ON kb_document_profiles(document_id)",
    "CREATE INDEX IF NOT EXISTS idx_kb_doc_profiles_owner ON kb_document_profiles(owner_id)",
    "CREATE INDEX IF NOT EXISTS idx_kb_file_rel_source ON kb_file_relations(source_document_id)",
    "CREATE INDEX IF NOT EXISTS idx_kb_file_rel_target ON kb_file_relations(target_document_id)",
    "CREATE INDEX IF NOT EXISTS idx_kb_file_rel_owner ON kb_file_relations(owner_id)",
]

# ALTER 列补齐语句（幂等，ADD COLUMN IF NOT EXISTS）
_MIGRATION_STATEMENTS = [
    "ALTER TABLE kb_documents ADD COLUMN IF NOT EXISTS raw_status VARCHAR(32) DEFAULT 'pending'",
    "ALTER TABLE kb_documents ADD COLUMN IF NOT EXISTS fusion_status VARCHAR(32) DEFAULT 'pending'",
    "ALTER TABLE kb_page_fusions ADD COLUMN IF NOT EXISTS page_summary TEXT",
    "ALTER TABLE kb_page_fusions ADD COLUMN IF NOT EXISTS page_title VARCHAR(512)",
    "ALTER TABLE kb_page_fusions ADD COLUMN IF NOT EXISTS body_json JSON",
    "ALTER TABLE kb_page_fusions ADD COLUMN IF NOT EXISTS attributes_json JSON",
    "ALTER TABLE kb_page_fusions ADD COLUMN IF NOT EXISTS tags_json JSON",
    "ALTER TABLE kb_page_fusions ADD COLUMN IF NOT EXISTS conflicts_json JSON",
    "ALTER TABLE kb_page_fusions ADD COLUMN IF NOT EXISTS evidence_json JSON",
    "ALTER TABLE kb_page_fusions ADD COLUMN IF NOT EXISTS source_version INTEGER",
    "ALTER TABLE kb_page_fusions ADD COLUMN IF NOT EXISTS fusion_version INTEGER DEFAULT 1",
    "ALTER TABLE kb_page_fusions ADD COLUMN IF NOT EXISTS fusion_status VARCHAR(32) DEFAULT 'pending'",
    "ALTER TABLE kb_page_fusions ADD COLUMN IF NOT EXISTS confidence FLOAT",
]


async def ensure_kb_tables(db: AsyncSession) -> None:
    """确保所有 kb_* 表已创建。"""
    from .models import (  # noqa: F401 注册到 Base.metadata
        KbCatalog, KbDocument, KbChunk, KbPageFusion, KbRawData,
        KbDocumentProfile, KbFileRelation,
        KbEntityDictionary, KbEntityAlias, KbDisambiguation,
        KbGraphNode, KbGraphEdge, KbChunkEntity,
        KbEvidence, KbConclusionEvidence, KbEntityMergeLog,
        KbGovernanceCandidate,
    )
    kb_tables = [t for n, t in Base.metadata.tables.items() if n.startswith("kb_")]
    # 用原始连接执行建表（SQLAlchemy async 兼容）
    from app.database import engine
    async with engine.begin() as conn:
        await conn.run_sync(lambda c: Base.metadata.create_all(c, tables=kb_tables))
    logger.info("Ensured %d kb_* tables exist", len(kb_tables))


async def ensure_kb_indexes(db: AsyncSession) -> None:
    """确保关键索引存在（无痛迁移）。"""
    for stmt in _INDEX_STATEMENTS:
        try:
            await db.execute(text(stmt))
        except Exception as e:
            logger.warning("Index creation skipped (%s): %s", stmt[:60], e)
    await db.commit()
    logger.info("Ensured kb_* indexes")


async def ensure_migration_columns(db: AsyncSession) -> None:
    """无痛迁移：为已存在的旧表补齐新增列（create_all 不改旧表）。

    模块自带迁移 = create_all(新表) + ALTER IF NOT EXISTS(旧表加列)。
    """
    for stmt in _MIGRATION_STATEMENTS:
        try:
            await db.execute(text(stmt))
        except Exception as e:
            logger.warning("Migration skipped (%s): %s", stmt[:80], e)
    await db.commit()
    logger.info("Ensured migration columns on kb_documents and kb_page_fusions")


async def run_init(db: AsyncSession) -> None:
    """知识库模块启动初始化入口。"""
    await ensure_kb_tables(db)
    await ensure_kb_indexes(db)
    await ensure_migration_columns(db)


def _run_startup_init():
    """模块加载时调用：一次性建表 + 索引 + 列迁移（幂等）。

    处理两种场景：
    1. 主进程导入（无事件循环）→ asyncio.run() 独立执行
    2. Worker 进程导入（事件循环运行中）→ asyncio.ensure_future() 调度
    """
    import asyncio

    async def _init():
        from app.database import AsyncSessionLocal
        async with AsyncSessionLocal() as db:
            await ensure_kb_tables(db)
            await ensure_kb_indexes(db)
            await ensure_migration_columns(db)

    try:
        loop = asyncio.get_event_loop()
    except RuntimeError:
        loop = None

    if loop is not None and loop.is_running():
        # Worker 进程：事件循环在跑，用 ensure_future 调度
        asyncio.ensure_future(_init())
        logger.info("Scheduled kb startup init on running event loop")
    else:
        # 主进程：无事件循环，用 asyncio.run()
        try:
            asyncio.run(_init())
            logger.info("Knowledge module startup init complete")
        except Exception as e:
            logger.warning("Startup init failed (schema may be lazily repaired): %s", e)
