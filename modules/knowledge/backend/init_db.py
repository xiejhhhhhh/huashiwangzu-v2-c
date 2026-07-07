"""知识库模块表初始化：确保知识库表在数据库中存在，支持无痛列补齐。"""
import logging

from app.models.base import Base
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger("v2.knowledge").getChild("init_db")
_STARTUP_INIT_LOCK_KEY = 1262633101

# 知识库模块的所有表名
KB_TABLES = [
    "kb_catalogs", "kb_documents", "kb_chunks", "kb_page_fusions",
    "kb_raw_data", "kb_document_profiles", "kb_file_relations",
    "kb_entity_dictionary", "kb_entity_aliases", "kb_disambiguation",
    "kb_graph_nodes", "kb_graph_edges", "kb_chunk_entities",
    "kb_evidence", "kb_conclusion_evidence", "kb_entity_merge_log",
    "kb_governance_candidates", "kb_pipeline_runs",
    "kb_pipeline_stage_runs", "kb_analysis_artifacts", "kb_pipeline_stale",
    "kb_image_assets", "kb_image_similar_pairs", "kb_image_similarity_groups",
    "kb_content_objects", "kb_file_knowledge_links", "kb_ingest_batches",
    "kb_validation_reports", "kb_artifact_lineage", "kb_terms",
    "kb_term_occurrences", "kb_term_edges", "kb_fact_candidates",
    "kb_causal_candidates", "kb_query_contexts",
]

# 关键索引语句（幂等，CREATE INDEX IF NOT EXISTS）
_INDEX_STATEMENTS = [
    "CREATE INDEX IF NOT EXISTS idx_kb_documents_owner ON kb_documents(owner_id) WHERE NOT deleted",
    "CREATE INDEX IF NOT EXISTS idx_kb_documents_catalog ON kb_documents(catalog_id) WHERE NOT deleted",
    "CREATE INDEX IF NOT EXISTS idx_kb_documents_status ON kb_documents(parse_status)",
    "CREATE UNIQUE INDEX IF NOT EXISTS ux_kb_documents_owner_file_active ON kb_documents(owner_id, file_id) WHERE NOT deleted",
    "CREATE INDEX IF NOT EXISTS idx_kb_chunks_doc ON kb_chunks(document_id)",
    "CREATE INDEX IF NOT EXISTS idx_kb_chunks_owner ON kb_chunks(owner_id)",
    "CREATE INDEX IF NOT EXISTS idx_kb_chunks_doc_layer ON kb_chunks(document_id, index_layer)",
    "CREATE INDEX IF NOT EXISTS idx_kb_chunks_owner_layer ON kb_chunks(owner_id, index_layer)",
    "CREATE INDEX IF NOT EXISTS idx_kb_page_fusions_doc_page ON kb_page_fusions(document_id, page)",
    "CREATE INDEX IF NOT EXISTS idx_kb_entity_dict_owner ON kb_entity_dictionary(owner_id)",
    "CREATE INDEX IF NOT EXISTS idx_kb_graph_nodes_entity ON kb_graph_nodes(entity_id)",
    "CREATE INDEX IF NOT EXISTS idx_kb_graph_edges_source ON kb_graph_edges(source_node_id)",
    "CREATE INDEX IF NOT EXISTS idx_kb_graph_edges_target ON kb_graph_edges(target_node_id)",
    "CREATE INDEX IF NOT EXISTS idx_kb_evidence_entity ON kb_evidence(entity_id)",
    "CREATE INDEX IF NOT EXISTS idx_kb_evidence_raw_data ON kb_evidence(raw_data_id)",
    "CREATE INDEX IF NOT EXISTS idx_kb_evidence_page_fusion ON kb_evidence(page_fusion_id)",
    "CREATE INDEX IF NOT EXISTS idx_kb_evidence_artifact ON kb_evidence(artifact_id)",
    "CREATE INDEX IF NOT EXISTS idx_kb_evidence_doc_claim ON kb_evidence(document_id, claim_type)",
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
    "CREATE INDEX IF NOT EXISTS idx_kb_pipeline_runs_doc ON kb_pipeline_runs(document_id)",
    "CREATE INDEX IF NOT EXISTS idx_kb_pipeline_runs_status ON kb_pipeline_runs(status)",
    "CREATE INDEX IF NOT EXISTS idx_kb_pipeline_stage_runs_doc_stage ON kb_pipeline_stage_runs(document_id, stage)",
    "CREATE INDEX IF NOT EXISTS idx_kb_pipeline_stage_runs_run ON kb_pipeline_stage_runs(run_id)",
    "CREATE INDEX IF NOT EXISTS idx_kb_analysis_artifacts_doc_stage ON kb_analysis_artifacts(document_id, stage)",
    "CREATE INDEX IF NOT EXISTS idx_kb_analysis_artifacts_run ON kb_analysis_artifacts(pipeline_run_id)",
    "CREATE INDEX IF NOT EXISTS idx_kb_analysis_artifacts_status ON kb_analysis_artifacts(status)",
    "CREATE INDEX IF NOT EXISTS idx_kb_analysis_artifacts_input_hash ON kb_analysis_artifacts(input_hash)",
    "CREATE INDEX IF NOT EXISTS idx_kb_pipeline_stale_doc ON kb_pipeline_stale(document_id)",
    "CREATE INDEX IF NOT EXISTS idx_kb_image_assets_owner ON kb_image_assets(owner_id)",
    "CREATE INDEX IF NOT EXISTS idx_kb_image_assets_doc_page ON kb_image_assets(document_id, page)",
    "CREATE INDEX IF NOT EXISTS idx_kb_image_assets_hashes ON kb_image_assets(phash, dhash)",
    "CREATE INDEX IF NOT EXISTS idx_kb_image_assets_group ON kb_image_assets(similarity_group_id)",
    "CREATE INDEX IF NOT EXISTS idx_kb_image_pairs_owner_level ON kb_image_similar_pairs(owner_id, similarity_level)",
    "CREATE INDEX IF NOT EXISTS idx_kb_image_pairs_source ON kb_image_similar_pairs(source_asset_id)",
    "CREATE INDEX IF NOT EXISTS idx_kb_image_pairs_target ON kb_image_similar_pairs(target_asset_id)",
    "CREATE INDEX IF NOT EXISTS idx_kb_image_groups_owner ON kb_image_similarity_groups(owner_id)",
    "CREATE INDEX IF NOT EXISTS idx_kb_content_objects_owner ON kb_content_objects(owner_id)",
    "CREATE INDEX IF NOT EXISTS idx_kb_content_objects_md5 ON kb_content_objects(owner_id, md5_hash)",
    "CREATE INDEX IF NOT EXISTS idx_kb_content_objects_sha256 ON kb_content_objects(owner_id, sha256_hash)",
    "CREATE UNIQUE INDEX IF NOT EXISTS ux_kb_content_objects_owner_md5 ON kb_content_objects(owner_id, md5_hash) WHERE md5_hash IS NOT NULL",
    "CREATE UNIQUE INDEX IF NOT EXISTS ux_kb_content_objects_owner_sha256 ON kb_content_objects(owner_id, sha256_hash) WHERE sha256_hash IS NOT NULL",
    "CREATE INDEX IF NOT EXISTS idx_kb_content_objects_canonical_doc ON kb_content_objects(canonical_document_id)",
    "CREATE INDEX IF NOT EXISTS idx_kb_file_links_owner_role ON kb_file_knowledge_links(owner_id, link_role)",
    "CREATE INDEX IF NOT EXISTS idx_kb_file_links_content ON kb_file_knowledge_links(content_object_id)",
    "CREATE INDEX IF NOT EXISTS idx_kb_file_links_doc ON kb_file_knowledge_links(document_id)",
    "CREATE INDEX IF NOT EXISTS idx_kb_file_links_canonical_doc ON kb_file_knowledge_links(canonical_document_id)",
    "CREATE INDEX IF NOT EXISTS idx_kb_ingest_batches_owner ON kb_ingest_batches(owner_id, status)",
    "CREATE INDEX IF NOT EXISTS idx_kb_validation_reports_owner ON kb_validation_reports(owner_id, report_type)",
    "CREATE INDEX IF NOT EXISTS idx_kb_artifact_lineage_doc_stage ON kb_artifact_lineage(document_id, stage)",
    "CREATE INDEX IF NOT EXISTS idx_kb_artifact_lineage_reuse ON kb_artifact_lineage(reused_from_artifact_id)",
    "CREATE INDEX IF NOT EXISTS idx_kb_terms_owner_norm ON kb_terms(owner_id, normalized)",
    "CREATE INDEX IF NOT EXISTS idx_kb_terms_owner_type ON kb_terms(owner_id, term_type)",
    "CREATE INDEX IF NOT EXISTS idx_kb_term_occurrences_doc ON kb_term_occurrences(document_id)",
    "CREATE INDEX IF NOT EXISTS idx_kb_term_occurrences_term ON kb_term_occurrences(term_id)",
    "CREATE INDEX IF NOT EXISTS idx_kb_term_occurrences_source_hash ON kb_term_occurrences(owner_id, source_hash)",
    "CREATE UNIQUE INDEX IF NOT EXISTS ux_kb_term_occurrences_owner_source ON kb_term_occurrences(owner_id, source_hash) WHERE source_hash IS NOT NULL",
    "CREATE INDEX IF NOT EXISTS idx_kb_term_edges_source ON kb_term_edges(source_term_id)",
    "CREATE INDEX IF NOT EXISTS idx_kb_term_edges_target ON kb_term_edges(target_term_id)",
    "CREATE INDEX IF NOT EXISTS idx_kb_fact_candidates_doc ON kb_fact_candidates(document_id, status)",
    "CREATE INDEX IF NOT EXISTS idx_kb_fact_candidates_source_hash ON kb_fact_candidates(owner_id, source_hash)",
    "CREATE UNIQUE INDEX IF NOT EXISTS ux_kb_fact_candidates_owner_source ON kb_fact_candidates(owner_id, source_hash) WHERE source_hash IS NOT NULL",
    "CREATE INDEX IF NOT EXISTS idx_kb_causal_candidates_doc ON kb_causal_candidates(document_id, status)",
    "CREATE INDEX IF NOT EXISTS idx_kb_causal_candidates_source_hash ON kb_causal_candidates(owner_id, source_hash)",
    "CREATE UNIQUE INDEX IF NOT EXISTS ux_kb_causal_candidates_owner_source ON kb_causal_candidates(owner_id, source_hash) WHERE source_hash IS NOT NULL",
    "CREATE INDEX IF NOT EXISTS idx_kb_query_contexts_owner_hash ON kb_query_contexts(owner_id, query_hash)",
]

# ALTER 列补齐语句（幂等，ADD COLUMN IF NOT EXISTS）。
# 运行前仍先查 information_schema，避免列已存在时重复 ALTER 参与强锁竞争。
_MIGRATION_STATEMENTS = [
    ("kb_documents", "raw_status", "ALTER TABLE kb_documents ADD COLUMN IF NOT EXISTS raw_status VARCHAR(32) DEFAULT 'pending'"),
    ("kb_documents", "fusion_status", "ALTER TABLE kb_documents ADD COLUMN IF NOT EXISTS fusion_status VARCHAR(32) DEFAULT 'pending'"),
    ("kb_documents", "profile_status", "ALTER TABLE kb_documents ADD COLUMN IF NOT EXISTS profile_status VARCHAR(32) DEFAULT 'pending'"),
    ("kb_documents", "graph_status", "ALTER TABLE kb_documents ADD COLUMN IF NOT EXISTS graph_status VARCHAR(32) DEFAULT 'pending'"),
    ("kb_documents", "relation_status", "ALTER TABLE kb_documents ADD COLUMN IF NOT EXISTS relation_status VARCHAR(32) DEFAULT 'pending'"),
    ("kb_page_fusions", "page_summary", "ALTER TABLE kb_page_fusions ADD COLUMN IF NOT EXISTS page_summary TEXT"),
    ("kb_page_fusions", "page_title", "ALTER TABLE kb_page_fusions ADD COLUMN IF NOT EXISTS page_title VARCHAR(512)"),
    ("kb_page_fusions", "body_json", "ALTER TABLE kb_page_fusions ADD COLUMN IF NOT EXISTS body_json JSON"),
    ("kb_page_fusions", "attributes_json", "ALTER TABLE kb_page_fusions ADD COLUMN IF NOT EXISTS attributes_json JSON"),
    ("kb_page_fusions", "tags_json", "ALTER TABLE kb_page_fusions ADD COLUMN IF NOT EXISTS tags_json JSON"),
    ("kb_page_fusions", "conflicts_json", "ALTER TABLE kb_page_fusions ADD COLUMN IF NOT EXISTS conflicts_json JSON"),
    ("kb_page_fusions", "evidence_json", "ALTER TABLE kb_page_fusions ADD COLUMN IF NOT EXISTS evidence_json JSON"),
    ("kb_page_fusions", "source_version", "ALTER TABLE kb_page_fusions ADD COLUMN IF NOT EXISTS source_version INTEGER"),
    ("kb_page_fusions", "fusion_version", "ALTER TABLE kb_page_fusions ADD COLUMN IF NOT EXISTS fusion_version INTEGER DEFAULT 1"),
    ("kb_page_fusions", "fusion_status", "ALTER TABLE kb_page_fusions ADD COLUMN IF NOT EXISTS fusion_status VARCHAR(32) DEFAULT 'pending'"),
    ("kb_page_fusions", "confidence", "ALTER TABLE kb_page_fusions ADD COLUMN IF NOT EXISTS confidence FLOAT"),
    ("kb_documents", "content_package_id", "ALTER TABLE kb_documents ADD COLUMN IF NOT EXISTS content_package_id BIGINT"),
    ("kb_chunks", "block_id", "ALTER TABLE kb_chunks ADD COLUMN IF NOT EXISTS block_id VARCHAR(64)"),
    ("kb_chunks", "index_layer", "ALTER TABLE kb_chunks ADD COLUMN IF NOT EXISTS index_layer VARCHAR(32) DEFAULT 'base_parse'"),
    ("kb_chunks", "index_version", "ALTER TABLE kb_chunks ADD COLUMN IF NOT EXISTS index_version INTEGER DEFAULT 1"),
    ("kb_chunks", "source_stage", "ALTER TABLE kb_chunks ADD COLUMN IF NOT EXISTS source_stage VARCHAR(64) DEFAULT 'parse_index'"),
    ("kb_chunks", "source_ref_id", "ALTER TABLE kb_chunks ADD COLUMN IF NOT EXISTS source_ref_id BIGINT"),
    ("kb_raw_data", "status", "ALTER TABLE kb_raw_data ADD COLUMN IF NOT EXISTS status VARCHAR(32) DEFAULT 'done'"),
    ("kb_raw_data", "error_message", "ALTER TABLE kb_raw_data ADD COLUMN IF NOT EXISTS error_message TEXT"),
    ("kb_raw_data", "duration_ms", "ALTER TABLE kb_raw_data ADD COLUMN IF NOT EXISTS duration_ms INTEGER"),
    ("kb_page_fusions", "diagnostics_json", "ALTER TABLE kb_page_fusions ADD COLUMN IF NOT EXISTS diagnostics_json JSON"),
    ("kb_page_fusions", "error_message", "ALTER TABLE kb_page_fusions ADD COLUMN IF NOT EXISTS error_message TEXT"),
    ("kb_page_fusions", "duration_ms", "ALTER TABLE kb_page_fusions ADD COLUMN IF NOT EXISTS duration_ms INTEGER"),
    ("kb_document_profiles", "labels_json", "ALTER TABLE kb_document_profiles ADD COLUMN IF NOT EXISTS labels_json JSON"),
    ("kb_evidence", "raw_data_id", "ALTER TABLE kb_evidence ADD COLUMN IF NOT EXISTS raw_data_id BIGINT"),
    ("kb_evidence", "page_fusion_id", "ALTER TABLE kb_evidence ADD COLUMN IF NOT EXISTS page_fusion_id BIGINT"),
    ("kb_evidence", "artifact_id", "ALTER TABLE kb_evidence ADD COLUMN IF NOT EXISTS artifact_id BIGINT"),
    ("kb_evidence", "source_round", "ALTER TABLE kb_evidence ADD COLUMN IF NOT EXISTS source_round VARCHAR(32)"),
    ("kb_evidence", "claim_type", "ALTER TABLE kb_evidence ADD COLUMN IF NOT EXISTS claim_type VARCHAR(64)"),
    ("kb_evidence", "bbox_json", "ALTER TABLE kb_evidence ADD COLUMN IF NOT EXISTS bbox_json JSON"),
    ("kb_evidence", "offset_json", "ALTER TABLE kb_evidence ADD COLUMN IF NOT EXISTS offset_json JSON"),
    ("kb_evidence", "source_hash", "ALTER TABLE kb_evidence ADD COLUMN IF NOT EXISTS source_hash VARCHAR(64)"),
    ("kb_evidence", "prompt_hash", "ALTER TABLE kb_evidence ADD COLUMN IF NOT EXISTS prompt_hash VARCHAR(64)"),
    ("kb_evidence", "model_used", "ALTER TABLE kb_evidence ADD COLUMN IF NOT EXISTS model_used VARCHAR(128)"),
    ("kb_evidence", "diagnostics_json", "ALTER TABLE kb_evidence ADD COLUMN IF NOT EXISTS diagnostics_json JSON"),
    ("kb_fact_candidates", "source_hash", "ALTER TABLE kb_fact_candidates ADD COLUMN IF NOT EXISTS source_hash VARCHAR(64)"),
    ("kb_causal_candidates", "source_hash", "ALTER TABLE kb_causal_candidates ADD COLUMN IF NOT EXISTS source_hash VARCHAR(64)"),
    ("kb_image_assets", "storage_path", "ALTER TABLE kb_image_assets ADD COLUMN IF NOT EXISTS storage_path VARCHAR(512)"),
    ("kb_image_assets", "mime_type", "ALTER TABLE kb_image_assets ADD COLUMN IF NOT EXISTS mime_type VARCHAR(128)"),
    ("kb_image_assets", "byte_size", "ALTER TABLE kb_image_assets ADD COLUMN IF NOT EXISTS byte_size BIGINT"),
]

_KNOWLEDGE_PROMPT_CATEGORY = {
    "name": "knowledge",
    "description": "Knowledge module runtime prompts",
    "sort_order": 30,
}

_KNOWLEDGE_PROMPTS = [
    {
        "name": "knowledge_profile_system",
        "description": "Knowledge document profile generation system prompt",
        "content": """你是企业文档分析专家。请根据以下各页的融合内容，生成文件级画像。

企业资料范围：
- 这里是企业历史资料库，包含合规报告、备案/检验/质检资料、产品说明、配方/成分资料、营销文案、培训材料、协议合同、管理制度、数据表、图片/海报/物料页面等。
- 历史资料不等于无价值：请判断它更适合“当前可用参考、历史留档、合规备查、营销复用、低价值素材、待人工复核”中的哪类用途。
- 图片、海报、素材类资料只保留可检索文本、设计结构、业务标签和关联线索；不要要求存储图片二进制。

输出严格 JSON（不要 markdown 标记）：
{
  "subject": "文件主旨（一句话）",
  "doc_type": "基于正文证据自由返回具体中文类型，例如：品牌介绍、产品说明、营销文案、培训手册、数据报表、配方文件、会员方案、管理制度、协议合同、检验报告、备案报告、质检报告、海报素材、图片素材等；不要局限于示例",
  "chapter_structure": [{"title": "章节标题", "page": 1, "summary": "该章节内容"}],
  "core_conclusions": "核心结论（2-3句话）",
  "key_entities": [{"name": "实体名", "type": "产品/品牌/成分/人物/事件/其他", "relevance": "high"}],
  "doc_summary": "文档级摘要（3-5句话）",
  "searchable_phrases": ["搜索短语1", "搜索短语2"],
  "labels": {
    "business_tags": ["模型根据正文返回的业务标签"],
    "usage_tags": ["当前可用参考/历史留档/合规备查/营销复用/低价值素材/待人工复核"],
    "content_boundaries": ["使用边界，例如不得用于广告宣传、仅供内部归档、需人工复核等"],
    "business_objects": [{"name": "对象名", "type": "产品/品牌/报告编号/机构/素材用途/其他", "evidence_pages": [1]}],
    "evidence": [{"label": "标签或判断", "pages": [1], "excerpt": "支持该判断的短原文"}]
  },
  "applicable_scenarios": "适用场景描述",
  "expiry_risk": "none/low/medium/high"
}

分类要求：
1. 优先依据正文证据，而不是仅依据文件名或目录名。
2. doc_type 由你根据正文自由归纳，允许出现示例之外的企业资料类型。
3. 当正文与文件名冲突时，以正文结构和证据为准，并在摘要中保留可追溯线索。
4. 标签、边界、用途必须由正文证据或清晰页面结构支持；不能因为目录名看起来像某类资料就直接下结论。
5. 无法从正文确认时才使用“其他”，并在 labels.evidence 或 content_boundaries 中说明需要人工复核。
6. business_tags 用于知识库检索与后续 Agent 路由，保持短、准、可组合，不要输出空泛词。""",
    },
    {
        "name": "knowledge_entity_extraction",
        "description": "Knowledge graph entity and relationship extraction prompt",
        "content": """你是一个企业知识图谱实体抽取专家。请从以下文档内容中提取实体和关系。

提取规则：
1. 实体类型：人名、组织名、地名、产品名、术语、事件、其他
2. 关系类型：属于、位于、产生、包含、引用、相关、领导、拥有、参与
3. 每条实体/关系必须基于原文证据
4. 提取出的实体名称要规范化（全称优先）

返回 JSON 格式（不要加 markdown 代码块标记）：
{
  "entities": [
    {"name": "实体名", "category": "实体类型", "description": "简要描述"}
  ],
  "relationships": [
    {"source": "实体A", "target": "实体B", "relation": "关系类型", "description": "关系描述"}
  ]
}

如果无实体可抽，返回 {"entities": [], "relationships": []}。""",
    },
    {
        "name": "knowledge_page_fusion",
        "description": "Knowledge raw collection cross-validation page fusion prompt",
        "content": """你是企业文档内容融合专家。以下是对同一文档页的三轮独立采集结果，请交叉印证后输出融合内容。

规则：
1. 三轮一致的直接取信
2. 有两轮一致、一轮偏离的，采信多数，在 conflicts 中记录不一致
3. 三轮全不同时，按常识判断最合理的，置信度降低
4. 保持原文信息不丢失，禁止编造
5. 用中文输出

输出严格 JSON（不要 markdown 代码块标记）：
{
  "fused_text": "交叉印证后的权威正文",
  "page_summary": "一句话页面摘要",
  "page_title": "页面标题(如有)",
  "entities": [{"name": "实体名", "type": "人名/组织/产品/术语/事件/其他"}],
  "attributes": {"键": "值"},
  "tags": ["标签1", "标签2"],
  "conflicts": [{"type": "内容矛盾/数量矛盾/格式矛盾", "detail": "具体描述", "rounds": [1,2,3]}],
  "confidence": 0.85
}""",
    },
    {
        "name": "knowledge_page_fusion_legacy",
        "description": "Knowledge legacy chunk-to-page text fusion prompt",
        "content": """你是一个企业文档内容融合专家。请将以下分块内容合并为连贯的文本段落。

规则：
1. 保持原文信息不丢失
2. 消除分块造成的内容断裂
3. 保留原文的段落结构和逻辑顺序
4. 不要添加原文不存在的信息

返回融合后的纯文本（不要 markdown 标记）。""",
    },
    {
        "name": "knowledge_raw_ocr",
        "description": "Knowledge raw collection OCR prompt",
        "content": "请识别并提取图片中所有可见的文字内容，包括标题、正文、表格中的文字等。按原顺序输出。",
    },
    {
        "name": "knowledge_raw_vision",
        "description": "Knowledge raw collection visual composition prompt",
        "content": """请按企业知识库检索用途分析这张图片或页面，不要描述为二进制文件本身。

先判断素材类型：未加工素材/产品图/海报/展架/灯箱/宣传册页面/截图/表格/低信息量图片。

请保留可用于后续 Agent 检索和关联的文本信息与设计结构：
1. 可见文字：品牌、产品、功效、价格、活动、适用人群、警示语等，按阅读顺序整理。
2. 版式结构：标题区、主视觉、产品区、功效区、案例对比区、参数/表格区、二维码/联系方式、页脚等。
3. 视觉层级：主体是什么，哪些元素最醒目，信息从上到下/从左到右如何组织。
4. 关键视觉对象：产品瓶身/套盒/人物/肌肤对比/门店物料/背景图案等。
5. 颜色与风格：主色、辅助色、风格倾向，只记录对识别和复用有价值的信息。
6. 业务关联关键词：品牌、系列、产品、功效、使用场景、适合人群、物料用途。

如果判断为未加工素材或低信息量图片，只输出简短注释和可关联标签；不要强行编造业务含义。""",
    },
]


async def ensure_kb_tables(db: AsyncSession) -> None:
    """确保所有 kb_* 表已创建。"""
    from .models import (  # noqa: F401 注册到 Base.metadata
        KbAnalysisArtifact,
        KbArtifactLineage,
        KbCatalog,
        KbCausalCandidate,
        KbChunk,
        KbChunkEntity,
        KbConclusionEvidence,
        KbContentObject,
        KbDisambiguation,
        KbDocument,
        KbDocumentProfile,
        KbEntityAlias,
        KbEntityDictionary,
        KbEntityMergeLog,
        KbEvidence,
        KbFactCandidate,
        KbFileKnowledgeLink,
        KbFileRelation,
        KbGovernanceCandidate,
        KbGraphEdge,
        KbGraphNode,
        KbImageAsset,
        KbImageSimilarityGroup,
        KbImageSimilarPair,
        KbIngestBatch,
        KbPageFusion,
        KbPipelineRun,
        KbPipelineStageRun,
        KbPipelineStale,
        KbQueryContext,
        KbRawData,
        KbTerm,
        KbTermEdge,
        KbTermOccurrence,
        KbValidationReport,
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
    for table_name, column_name, stmt in _MIGRATION_STATEMENTS:
        try:
            exists = await db.scalar(
                text(
                    """
                    SELECT 1
                    FROM information_schema.columns
                    WHERE table_schema = current_schema()
                      AND table_name = :table_name
                      AND column_name = :column_name
                    LIMIT 1
                    """
                ),
                {"table_name": table_name, "column_name": column_name},
            )
            if exists:
                continue
            await db.execute(text(stmt))
        except Exception as e:
            logger.warning("Migration skipped (%s): %s", stmt[:80], e)
    await db.commit()
    logger.info("Ensured migration columns on kb_documents and kb_page_fusions")


async def ensure_prompt_templates(db: AsyncSession) -> None:
    """Seed knowledge runtime prompts into the framework prompt registry."""
    from app.models.prompt import PromptCategory, PromptTemplate

    result = await db.execute(
        select(PromptCategory).where(PromptCategory.name == _KNOWLEDGE_PROMPT_CATEGORY["name"])
    )
    category = result.scalar_one_or_none()
    if category is None:
        category = PromptCategory(**_KNOWLEDGE_PROMPT_CATEGORY)
        db.add(category)
        await db.flush()

    seeded = 0
    for item in _KNOWLEDGE_PROMPTS:
        existing = await db.execute(
            select(PromptTemplate.id).where(PromptTemplate.name == item["name"]).limit(1)
        )
        if existing.scalar_one_or_none():
            continue
        db.add(
            PromptTemplate(
                category_id=category.id,
                name=item["name"],
                content=item["content"],
                variables={},
                description=item["description"],
                is_default=True,
                is_enabled=True,
            )
        )
        seeded += 1

    await db.commit()
    logger.info("Ensured knowledge prompt templates (seeded=%d)", seeded)


async def _run_with_startup_init_lock(db: AsyncSession) -> None:
    """Run knowledge schema init in one process without queuing every worker."""
    acquired = await db.scalar(text("SELECT pg_try_advisory_lock(:lock_key)"), {"lock_key": _STARTUP_INIT_LOCK_KEY})
    if not acquired:
        await db.commit()
        logger.info("Knowledge startup init skipped; another process is handling schema init")
        return
    try:
        await ensure_kb_tables(db)
        await ensure_migration_columns(db)
        await ensure_kb_indexes(db)
        await ensure_prompt_templates(db)
    finally:
        try:
            await db.execute(text("SELECT pg_advisory_unlock(:lock_key)"), {"lock_key": _STARTUP_INIT_LOCK_KEY})
            await db.commit()
        except Exception as exc:
            logger.warning("Knowledge startup init lock release failed: %s", exc)


async def run_init(db: AsyncSession) -> None:
    """知识库模块启动初始化入口。"""
    await _run_with_startup_init_lock(db)


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
            await _run_with_startup_init_lock(db)

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
