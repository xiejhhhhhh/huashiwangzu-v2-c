"""知识库模块表初始化：确保知识库表在数据库中存在，支持无痛列补齐。"""
import logging
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession
from app.models.base import Base

logger = logging.getLogger("v2.knowledge.init_db")

# 知识库模块的所有表名
KB_TABLES = [
    "kb_catalogs", "kb_documents", "kb_chunks", "kb_page_fusions",
    "kb_entity_dictionary", "kb_entity_aliases", "kb_disambiguation",
    "kb_graph_nodes", "kb_graph_edges", "kb_chunk_entities",
    "kb_evidence", "kb_conclusion_evidence", "kb_entity_merge_log",
    "kb_governance_candidates",
]


async def ensure_kb_tables(db: AsyncSession) -> None:
    """确保所有 kb_* 表已创建。"""
    from .models import (  # noqa: F401 注册到 Base.metadata
        KbCatalog, KbDocument, KbChunk, KbPageFusion,
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
    index_statements = [
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
    ]
    for stmt in index_statements:
        try:
            await db.execute(text(stmt))
        except Exception as e:
            logger.warning("Index creation skipped (%s): %s", stmt[:60], e)
    await db.commit()
    logger.info("Ensured kb_* indexes")


async def run_init(db: AsyncSession) -> None:
    """知识库模块启动初始化入口。"""
    await ensure_kb_tables(db)
    await ensure_kb_indexes(db)
