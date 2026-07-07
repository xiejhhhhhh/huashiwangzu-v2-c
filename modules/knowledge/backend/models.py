"""知识库模块业务表。表名 kb_* 前缀，不加外键到框架表/其他模块表。"""
from datetime import datetime

from app.models.base import Base, TimestampMixin
from pgvector.sqlalchemy import Vector
from sqlalchemy import JSON, BigInteger, Boolean, DateTime, Float, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

KB_TABLE_ARGS_EXTEND = {"extend_existing": True}


class KbCatalog(Base, TimestampMixin):
    """知识库目录树。"""
    __tablename__ = "kb_catalogs"
    __table_args__ = KB_TABLE_ARGS_EXTEND
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    owner_id: Mapped[int] = mapped_column(Integer, nullable=False)
    name: Mapped[str] = mapped_column(String(256), nullable=False)
    parent_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    sort_order: Mapped[int] = mapped_column(Integer, default=0)
    deleted: Mapped[bool] = mapped_column(Boolean, default=False)


class KbDocument(Base, TimestampMixin):
    """知识库文档/资料记录。文件本体走框架文件存储，这里只存逻辑引用。"""
    __tablename__ = "kb_documents"
    __table_args__ = KB_TABLE_ARGS_EXTEND
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    owner_id: Mapped[int] = mapped_column(Integer, nullable=False)
    catalog_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    file_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    filename: Mapped[str] = mapped_column(String(512), nullable=False)
    extension: Mapped[str] = mapped_column(String(32), default="")
    file_size: Mapped[int] = mapped_column(BigInteger, default=0)
    mime_type: Mapped[str] = mapped_column(String(128), default="")
    # 解析状态：pending/parsing/done/error
    parse_status: Mapped[str] = mapped_column(String(32), default="pending")
    parse_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    # 关联的内容包 ID（框架级 Content Package）
    content_package_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True, comment="Linked content package id")
    # 向量化状态：pending/indexing/done/error
    vector_status: Mapped[str] = mapped_column(String(32), default="pending")
    # 原始采集状态：pending/collecting/done/failed
    raw_status: Mapped[str] = mapped_column(String(32), default="pending")
    # 页级融合状态：pending/running/done/failed
    fusion_status: Mapped[str] = mapped_column(String(32), default="pending")
    # 文档画像/图谱/关联阶段状态
    profile_status: Mapped[str] = mapped_column(String(32), default="pending")
    graph_status: Mapped[str] = mapped_column(String(32), default="pending")
    relation_status: Mapped[str] = mapped_column(String(32), default="pending")
    # 解析计数
    total_chunks: Mapped[int] = mapped_column(Integer, default=0)
    total_pages: Mapped[int] = mapped_column(Integer, default=0)
    # 摘要（由 LLM 生成）
    summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    # 解析任务 worker 锁（防多 worker 重复消费）
    parse_worker_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    parse_started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    vector_worker_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    vector_started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    deleted: Mapped[bool] = mapped_column(Boolean, default=False)


class KbChunk(Base, TimestampMixin):
    """解析后的内容块。每块包含原文、页号、类型、向量。"""
    __tablename__ = "kb_chunks"
    __table_args__ = KB_TABLE_ARGS_EXTEND
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    document_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    owner_id: Mapped[int] = mapped_column(Integer, nullable=False)
    page: Mapped[int | None] = mapped_column(Integer, nullable=True)
    chunk_index: Mapped[int] = mapped_column(Integer, default=0)
    block_type: Mapped[str] = mapped_column(String(32), default="段落")  # 段落/标题/表格/图片/代码
    text: Mapped[str] = mapped_column(Text, default="")
    embedding: Mapped[list[float] | None] = mapped_column(Vector(1024), nullable=True)
    resource_ref: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # Content Package block_id for cross-reference
    block_id: Mapped[str | None] = mapped_column(String(64), nullable=True, comment="Content Package block id")
    index_layer: Mapped[str] = mapped_column(String(32), default="base_parse")
    index_version: Mapped[int] = mapped_column(Integer, default=1)
    source_stage: Mapped[str] = mapped_column(String(64), default="parse_index")
    source_ref_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    # 关键词（用于全文检索）
    keywords: Mapped[str | None] = mapped_column(Text, nullable=True)


class KbPageFusion(Base, TimestampMixin):
    """页级融合：三轮交叉印证后的单页权威描述（第4层）。"""
    __tablename__ = "kb_page_fusions"
    __table_args__ = KB_TABLE_ARGS_EXTEND
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    document_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    owner_id: Mapped[int] = mapped_column(Integer, nullable=False)
    page: Mapped[int] = mapped_column(Integer, nullable=False)
    # 融合正文（三轮交叉印证后的权威描述）
    fused_text: Mapped[str] = mapped_column(Text, default="")
    # 页面摘要
    page_summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    page_title: Mapped[str | None] = mapped_column(String(512), nullable=True)
    # 结构化提炼（JSON）
    body_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    attributes_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    tags_json: Mapped[list | None] = mapped_column(JSON, nullable=True)
    # 冲突记录（三轮矛盾细节）
    conflicts_json: Mapped[list | None] = mapped_column(JSON, nullable=True)
    # 证据引用（指向 kb_raw_data 的记录 ID）
    evidence_json: Mapped[list | None] = mapped_column(JSON, nullable=True)
    # 版本控制（支持重建上层不改原始数据）
    source_version: Mapped[int | None] = mapped_column(Integer, nullable=True)
    fusion_version: Mapped[int] = mapped_column(Integer, default=1)
    fusion_status: Mapped[str] = mapped_column(String(32), default="pending")
    # 融合置信度（0-1）
    confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    # 知识图谱增强后的融合文本（原有字段保留向下兼容）
    enhanced_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    # 页级诊断：fallback/LLM/索引等结构化信息
    diagnostics_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    duration_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)


class KbRawData(Base, TimestampMixin):
    """原始层：多轮独立采集结果，落盘后只读不可变。"""
    __tablename__ = "kb_raw_data"
    __table_args__ = KB_TABLE_ARGS_EXTEND
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    document_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    file_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    owner_id: Mapped[int] = mapped_column(Integer, nullable=False)
    page: Mapped[int] = mapped_column(Integer, nullable=False)
    round: Mapped[int] = mapped_column(Integer, nullable=False)   # 1=文本 2=OCR 3=视觉构成
    source_type: Mapped[str] = mapped_column(String(32), nullable=False)  # text/ocr/vision
    content: Mapped[str] = mapped_column(Text, default="")
    model_used: Mapped[str | None] = mapped_column(String(64), nullable=True)
    confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    metadata_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    content_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    # round 级诊断：done/degraded/failed，保留失败原因和耗时
    status: Mapped[str] = mapped_column(String(32), default="done")
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    duration_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)


class KbEntityDictionary(Base, TimestampMixin):
    """实体词典。"""
    __tablename__ = "kb_entity_dictionary"
    __table_args__ = KB_TABLE_ARGS_EXTEND
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    owner_id: Mapped[int] = mapped_column(Integer, nullable=False)
    name: Mapped[str] = mapped_column(String(256), nullable=False)
    category: Mapped[str] = mapped_column(String(64), default="通用")  # 人名/组织/地点/术语/产品/事件/通用
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(32), default="confirmed")  # candidate/confirmed/merged/archived
    source: Mapped[str] = mapped_column(String(64), default="extraction")  # extraction/manual/import


class KbEntityAlias(Base, TimestampMixin):
    """实体别名。"""
    __tablename__ = "kb_entity_aliases"
    __table_args__ = KB_TABLE_ARGS_EXTEND
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    owner_id: Mapped[int] = mapped_column(Integer, nullable=False)
    entity_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    alias: Mapped[str] = mapped_column(String(256), nullable=False)


class KbDisambiguation(Base, TimestampMixin):
    """歧义词：同一词形对应多个实体。"""
    __tablename__ = "kb_disambiguation"
    __table_args__ = KB_TABLE_ARGS_EXTEND
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    owner_id: Mapped[int] = mapped_column(Integer, nullable=False)
    term: Mapped[str] = mapped_column(String(256), nullable=False)
    entity_ids: Mapped[list] = mapped_column(JSON, default=list)
    resolved: Mapped[bool] = mapped_column(Boolean, default=False)


class KbGraphNode(Base, TimestampMixin):
    """知识图谱节点。"""
    __tablename__ = "kb_graph_nodes"
    __table_args__ = KB_TABLE_ARGS_EXTEND
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    owner_id: Mapped[int] = mapped_column(Integer, nullable=False)
    entity_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    label: Mapped[str] = mapped_column(String(256), nullable=False)
    category: Mapped[str] = mapped_column(String(64), default="通用")
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    # 节点属性（JSON）
    properties: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    # 布局坐标（可视化用）
    fx: Mapped[float | None] = mapped_column(Float, nullable=True)
    fy: Mapped[float | None] = mapped_column(Float, nullable=True)


class KbGraphEdge(Base, TimestampMixin):
    """知识图谱边。"""
    __tablename__ = "kb_graph_edges"
    __table_args__ = KB_TABLE_ARGS_EXTEND
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    owner_id: Mapped[int] = mapped_column(Integer, nullable=False)
    source_node_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    target_node_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    relation: Mapped[str] = mapped_column(String(128), nullable=False)  # 属于/位于/产生/包含/引用/相关
    weight: Mapped[float] = mapped_column(Float, default=1.0)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)


class KbChunkEntity(Base, TimestampMixin):
    """块-实体关联（多对多）。"""
    __tablename__ = "kb_chunk_entities"
    __table_args__ = KB_TABLE_ARGS_EXTEND
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    owner_id: Mapped[int] = mapped_column(Integer, nullable=False)
    chunk_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    entity_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    document_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    confidence: Mapped[float] = mapped_column(Float, default=0.0)


class KbEvidence(Base, TimestampMixin):
    """证据：实体在某文档某页的原文依据。"""
    __tablename__ = "kb_evidence"
    __table_args__ = KB_TABLE_ARGS_EXTEND
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    owner_id: Mapped[int] = mapped_column(Integer, nullable=False)
    entity_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    document_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    chunk_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    page: Mapped[int | None] = mapped_column(Integer, nullable=True)
    excerpt: Mapped[str] = mapped_column(Text, nullable=False)
    confidence: Mapped[float] = mapped_column(Float, default=0.0)
    status: Mapped[str] = mapped_column(String(32), default="pending")  # pending/confirmed/rejected
    raw_data_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    page_fusion_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    artifact_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    source_round: Mapped[str | None] = mapped_column(String(32), nullable=True)
    claim_type: Mapped[str | None] = mapped_column(String(64), nullable=True)
    bbox_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    offset_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    source_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    prompt_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    model_used: Mapped[str | None] = mapped_column(String(128), nullable=True)
    diagnostics_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)


class KbConclusionEvidence(Base, TimestampMixin):
    """结论-证据关联。"""
    __tablename__ = "kb_conclusion_evidence"
    __table_args__ = KB_TABLE_ARGS_EXTEND
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    owner_id: Mapped[int] = mapped_column(Integer, nullable=False)
    conclusion: Mapped[str] = mapped_column(Text, nullable=False)
    evidence_ids: Mapped[list] = mapped_column(JSON, default=list)
    document_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    confidence: Mapped[float] = mapped_column(Float, default=0.0)


class KbEntityMergeLog(Base, TimestampMixin):
    """实体合并记录。"""
    __tablename__ = "kb_entity_merge_log"
    __table_args__ = KB_TABLE_ARGS_EXTEND
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    owner_id: Mapped[int] = mapped_column(Integer, nullable=False)
    source_entity_ids: Mapped[list] = mapped_column(JSON, default=list)
    target_entity_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    merged_by: Mapped[int] = mapped_column(Integer, nullable=False)
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)


class KbGovernanceCandidate(Base, TimestampMixin):
    """治理候选：待审计/校准的抽取记录。"""
    __tablename__ = "kb_governance_candidates"
    __table_args__ = KB_TABLE_ARGS_EXTEND
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    owner_id: Mapped[int] = mapped_column(Integer, nullable=False)
    document_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    entity_name: Mapped[str] = mapped_column(String(256), nullable=False)
    category: Mapped[str] = mapped_column(String(64), default="通用")
    excerpt: Mapped[str] = mapped_column(Text, default="")
    confidence: Mapped[float] = mapped_column(Float, default=0.0)
    audit_status: Mapped[str] = mapped_column(String(32), default="pending")  # pending/approved/rejected/merged
    reviewed_by: Mapped[int | None] = mapped_column(Integer, nullable=True)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class KbDocumentProfile(Base, TimestampMixin):
    """第5层文件画像：文件级主旨/摘要/结构（参考V1 知识_文档画像）。"""
    __tablename__ = "kb_document_profiles"
    __table_args__ = KB_TABLE_ARGS_EXTEND
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    document_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    owner_id: Mapped[int] = mapped_column(Integer, nullable=False)
    # 文件主题
    subject: Mapped[str | None] = mapped_column(String(512), nullable=True)
    # 资料类型（产品说明/品牌介绍/培训手册/数据报表 等）
    doc_type: Mapped[str | None] = mapped_column(String(128), nullable=True)
    # 章节结构 JSON
    chapter_structure: Mapped[list | None] = mapped_column(JSON, nullable=True)
    # 核心结论
    core_conclusions: Mapped[str | None] = mapped_column(Text, nullable=True)
    # 关键实体 JSON
    key_entities: Mapped[list | None] = mapped_column(JSON, nullable=True)
    # 文档级摘要
    doc_summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    # 可检索短语 JSON
    searchable_phrases: Mapped[list | None] = mapped_column(JSON, nullable=True)
    # 模型返回的文档级标签、边界、证据页等结构化分类信息
    labels_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    # 适用场景
    applicable_scenarios: Mapped[str | None] = mapped_column(Text, nullable=True)
    # 过期风险
    expiry_risk: Mapped[str | None] = mapped_column(String(32), nullable=True)
    # 画像置信度
    confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    # 画像版本
    profile_version: Mapped[int] = mapped_column(Integer, default=1)
    # 嵌入向量（用于跨文件相似度计算）
    profile_embedding: Mapped[list | None] = mapped_column(JSON, nullable=True)


class KbFileRelation(Base, TimestampMixin):
    """第7层跨文件动态关联（★华哥最看重）。"""
    __tablename__ = "kb_file_relations"
    __table_args__ = KB_TABLE_ARGS_EXTEND
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    owner_id: Mapped[int] = mapped_column(Integer, nullable=False)
    source_document_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    target_document_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    # 关系类型
    relation_type: Mapped[str] = mapped_column(String(64), nullable=False)  # semantic_similar/entity_overlap/hierarchy/reference
    # 相似度分数
    similarity_score: Mapped[float] = mapped_column(Float, default=0.0)
    # 共同实体 JSON
    shared_entities: Mapped[list | None] = mapped_column(JSON, nullable=True)
    # 关联证据（具体描述为什么关联）
    evidence: Mapped[str | None] = mapped_column(Text, nullable=True)
    # 双向边权重
    weight: Mapped[float] = mapped_column(Float, default=1.0)


class KbContentObject(Base, TimestampMixin):
    """V3 内容对象：同一份物理内容只对应一个 canonical 知识对象。"""
    __tablename__ = "kb_content_objects"
    __table_args__ = (
        UniqueConstraint("owner_id", "md5_hash", name="uq_kb_content_objects_owner_md5"),
        UniqueConstraint("owner_id", "sha256_hash", name="uq_kb_content_objects_owner_sha256"),
        KB_TABLE_ARGS_EXTEND,
    )
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    owner_id: Mapped[int] = mapped_column(Integer, nullable=False)
    md5_hash: Mapped[str | None] = mapped_column(String(32), nullable=True)
    sha256_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    file_size: Mapped[int] = mapped_column(BigInteger, default=0)
    mime_type: Mapped[str] = mapped_column(String(128), default="")
    extension: Mapped[str] = mapped_column(String(32), default="")
    canonical_document_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    canonical_file_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    status: Mapped[str] = mapped_column(String(32), default="active")
    diagnostics_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)


class KbFileKnowledgeLink(Base, TimestampMixin):
    """V3 文件实例到 canonical 知识对象的显式血缘链接。"""
    __tablename__ = "kb_file_knowledge_links"
    __table_args__ = (
        UniqueConstraint("owner_id", "file_id", name="uq_kb_file_links_owner_file"),
        KB_TABLE_ARGS_EXTEND,
    )
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    owner_id: Mapped[int] = mapped_column(Integer, nullable=False)
    file_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    content_object_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    document_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    canonical_document_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    canonical_file_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    link_role: Mapped[str] = mapped_column(String(32), default="canonical")
    reuse_reason: Mapped[str | None] = mapped_column(String(64), nullable=True)
    md5_hash: Mapped[str | None] = mapped_column(String(32), nullable=True)
    storage_path: Mapped[str | None] = mapped_column(String(512), nullable=True)
    source_name_snapshot: Mapped[str | None] = mapped_column(String(512), nullable=True)
    source_extension_snapshot: Mapped[str | None] = mapped_column(String(32), nullable=True)
    source_folder_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    ingest_batch_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    status: Mapped[str] = mapped_column(String(32), default="active")
    diagnostics_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)


class KbIngestBatch(Base, TimestampMixin):
    """V3 导入批次账本，用于企业微盘批量验收和回滚说明。"""
    __tablename__ = "kb_ingest_batches"
    __table_args__ = KB_TABLE_ARGS_EXTEND
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    owner_id: Mapped[int] = mapped_column(Integer, nullable=False)
    name: Mapped[str] = mapped_column(String(256), default="")
    source_root: Mapped[str | None] = mapped_column(Text, nullable=True)
    source_kind: Mapped[str] = mapped_column(String(64), default="manual")
    total_files: Mapped[int] = mapped_column(Integer, default=0)
    distinct_content_count: Mapped[int] = mapped_column(Integer, default=0)
    duplicate_file_count: Mapped[int] = mapped_column(Integer, default=0)
    canonical_document_count: Mapped[int] = mapped_column(Integer, default=0)
    failed_count: Mapped[int] = mapped_column(Integer, default=0)
    status: Mapped[str] = mapped_column(String(32), default="running")
    summary_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class KbValidationReport(Base, TimestampMixin):
    """V3 验收报告：保存批次覆盖、重复复用、失败项和抽检结论。"""
    __tablename__ = "kb_validation_reports"
    __table_args__ = KB_TABLE_ARGS_EXTEND
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    owner_id: Mapped[int] = mapped_column(Integer, nullable=False)
    batch_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    scope: Mapped[str] = mapped_column(String(128), default="knowledge_v3")
    report_type: Mapped[str] = mapped_column(String(64), default="batch_validation")
    status: Mapped[str] = mapped_column(String(32), default="done")
    metrics_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    findings_json: Mapped[list | None] = mapped_column(JSON, nullable=True)
    recommendations_json: Mapped[list | None] = mapped_column(JSON, nullable=True)
    generated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class KbArtifactLineage(Base, TimestampMixin):
    """V3 产物血缘：说明一个 artifact 是新跑、复用还是派生。"""
    __tablename__ = "kb_artifact_lineage"
    __table_args__ = (
        UniqueConstraint("artifact_id", name="uq_kb_artifact_lineage_artifact"),
        KB_TABLE_ARGS_EXTEND,
    )
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    owner_id: Mapped[int] = mapped_column(Integer, nullable=False)
    artifact_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    document_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    stage: Mapped[str] = mapped_column(String(64), nullable=False)
    unit_type: Mapped[str] = mapped_column(String(32), default="document")
    unit_key: Mapped[str] = mapped_column(String(128), default="document")
    source_artifact_ids: Mapped[list | None] = mapped_column(JSON, nullable=True)
    reused_from_artifact_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    reuse_type: Mapped[str] = mapped_column(String(32), default="new")
    input_hash: Mapped[str] = mapped_column(String(64), default="")
    output_hash: Mapped[str] = mapped_column(String(64), default="")
    schema_version: Mapped[str] = mapped_column(String(32), default="")
    diagnostics_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)


class KbTerm(Base, TimestampMixin):
    """V3 词项节点：品牌、产品、成分、备案号、别名和自由业务标签。"""
    __tablename__ = "kb_terms"
    __table_args__ = (
        UniqueConstraint("owner_id", "normalized", "term_type", name="uq_kb_terms_owner_norm_type"),
        KB_TABLE_ARGS_EXTEND,
    )
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    owner_id: Mapped[int] = mapped_column(Integer, nullable=False)
    term: Mapped[str] = mapped_column(String(256), nullable=False)
    normalized: Mapped[str] = mapped_column(String(256), nullable=False)
    term_type: Mapped[str] = mapped_column(String(64), default="term")
    language: Mapped[str] = mapped_column(String(16), default="mixed")
    semantic_bucket: Mapped[int] = mapped_column(Integer, default=0)
    category_bucket: Mapped[int] = mapped_column(Integer, default=0)
    exact_hash: Mapped[str] = mapped_column(String(64), default="")
    source: Mapped[str] = mapped_column(String(64), default="derived")
    status: Mapped[str] = mapped_column(String(32), default="active")
    confidence: Mapped[float | None] = mapped_column(Float, nullable=True)


class KbTermOccurrence(Base, TimestampMixin):
    """V3 词项出现位置，用于可解释召回和后续治理。"""
    __tablename__ = "kb_term_occurrences"
    __table_args__ = (
        UniqueConstraint("owner_id", "source_hash", name="uq_kb_term_occurrences_owner_source"),
        KB_TABLE_ARGS_EXTEND,
    )
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    owner_id: Mapped[int] = mapped_column(Integer, nullable=False)
    term_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    document_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    chunk_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    page_fusion_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    evidence_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    artifact_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    page: Mapped[int | None] = mapped_column(Integer, nullable=True)
    source_type: Mapped[str] = mapped_column(String(64), default="derived")
    position: Mapped[int | None] = mapped_column(Integer, nullable=True)
    weight: Mapped[float] = mapped_column(Float, default=1.0)
    context: Mapped[str | None] = mapped_column(Text, nullable=True)
    source_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)


class KbTermEdge(Base, TimestampMixin):
    """V3 词项边：别名、共现、上下位、近义和业务关联。"""
    __tablename__ = "kb_term_edges"
    __table_args__ = (
        UniqueConstraint("owner_id", "source_term_id", "target_term_id", "edge_type", name="uq_kb_term_edges_owner_pair_type"),
        KB_TABLE_ARGS_EXTEND,
    )
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    owner_id: Mapped[int] = mapped_column(Integer, nullable=False)
    source_term_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    target_term_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    edge_type: Mapped[str] = mapped_column(String(64), default="co_occurs")
    weight: Mapped[float] = mapped_column(Float, default=1.0)
    evidence_ids: Mapped[list | None] = mapped_column(JSON, nullable=True)
    source_artifact_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    decision_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    status: Mapped[str] = mapped_column(String(32), default="active")


class KbFactCandidate(Base, TimestampMixin):
    """V3 候选事实：先沉淀混沌结果，后治理，不硬编码业务枚举。"""
    __tablename__ = "kb_fact_candidates"
    __table_args__ = (
        UniqueConstraint("owner_id", "source_hash", name="uq_kb_fact_candidates_owner_source"),
        KB_TABLE_ARGS_EXTEND,
    )
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    owner_id: Mapped[int] = mapped_column(Integer, nullable=False)
    document_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    page: Mapped[int | None] = mapped_column(Integer, nullable=True)
    subject: Mapped[str | None] = mapped_column(String(256), nullable=True)
    predicate: Mapped[str | None] = mapped_column(String(128), nullable=True)
    object_value: Mapped[str | None] = mapped_column(Text, nullable=True)
    claim_text: Mapped[str] = mapped_column(Text, default="")
    evidence_ids: Mapped[list | None] = mapped_column(JSON, nullable=True)
    source_artifact_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    source_type: Mapped[str] = mapped_column(String(64), default="derived")
    source_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    status: Mapped[str] = mapped_column(String(32), default="candidate")
    diagnostics_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)


class KbCausalCandidate(Base, TimestampMixin):
    """V3 因果候选：必须保留上下文和证据，不能直接当作已确认事实。"""
    __tablename__ = "kb_causal_candidates"
    __table_args__ = (
        UniqueConstraint("owner_id", "source_hash", name="uq_kb_causal_candidates_owner_source"),
        KB_TABLE_ARGS_EXTEND,
    )
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    owner_id: Mapped[int] = mapped_column(Integer, nullable=False)
    document_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    page: Mapped[int | None] = mapped_column(Integer, nullable=True)
    cause: Mapped[str] = mapped_column(Text, default="")
    effect: Mapped[str] = mapped_column(Text, default="")
    relation: Mapped[str] = mapped_column(String(64), default="causal_candidate")
    context: Mapped[str | None] = mapped_column(Text, nullable=True)
    evidence_ids: Mapped[list | None] = mapped_column(JSON, nullable=True)
    source_artifact_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    source_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    status: Mapped[str] = mapped_column(String(32), default="candidate")
    diagnostics_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)


class KbQueryContext(Base, TimestampMixin):
    """V3 查询上下文：记录一次查询如何被词项图、证据和因果候选增强。"""
    __tablename__ = "kb_query_contexts"
    __table_args__ = KB_TABLE_ARGS_EXTEND
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    owner_id: Mapped[int] = mapped_column(Integer, nullable=False)
    query: Mapped[str] = mapped_column(Text, default="")
    normalized_query: Mapped[str] = mapped_column(Text, default="")
    query_hash: Mapped[str] = mapped_column(String(64), default="")
    expanded_terms: Mapped[list | None] = mapped_column(JSON, nullable=True)
    related_terms: Mapped[list | None] = mapped_column(JSON, nullable=True)
    causal_links: Mapped[list | None] = mapped_column(JSON, nullable=True)
    facts: Mapped[list | None] = mapped_column(JSON, nullable=True)
    evidence_refs: Mapped[list | None] = mapped_column(JSON, nullable=True)
    result_document_ids: Mapped[list | None] = mapped_column(JSON, nullable=True)
    diagnostics_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)


class KbPipelineRun(Base, TimestampMixin):
    """一次知识库全链路运行的持久诊断账本。"""
    __tablename__ = "kb_pipeline_runs"
    __table_args__ = KB_TABLE_ARGS_EXTEND
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    document_id: Mapped[int] = mapped_column(BigInteger, nullable=False, index=True)
    owner_id: Mapped[int] = mapped_column(Integer, nullable=False)
    file_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    task_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    trigger: Mapped[str] = mapped_column(String(64), default="kb_pipeline_stage")
    status: Mapped[str] = mapped_column(String(32), default="running")
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    diagnostics_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class KbPipelineStageRun(Base, TimestampMixin):
    """Pipeline stage 级运行结果，承接 degraded/失败诊断和扩展指标。"""
    __tablename__ = "kb_pipeline_stage_runs"
    __table_args__ = KB_TABLE_ARGS_EXTEND
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    run_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True, index=True)
    document_id: Mapped[int] = mapped_column(BigInteger, nullable=False, index=True)
    owner_id: Mapped[int] = mapped_column(Integer, nullable=False)
    stage: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    artifact_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    metrics_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    duration_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)


class KbAnalysisArtifact(Base, TimestampMixin):
    """Stable analysis artifact ledger for resumable knowledge stages."""
    __tablename__ = "kb_analysis_artifacts"
    __table_args__ = KB_TABLE_ARGS_EXTEND
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    owner_id: Mapped[int] = mapped_column(Integer, nullable=False)
    document_id: Mapped[int] = mapped_column(BigInteger, nullable=False, index=True)
    file_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    task_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    pipeline_run_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True, index=True)
    stage: Mapped[str] = mapped_column(String(64), nullable=False)
    unit_type: Mapped[str] = mapped_column(String(32), default="document")
    unit_key: Mapped[str] = mapped_column(String(128), default="document")
    source_artifact_ids: Mapped[list | None] = mapped_column(JSON, nullable=True)
    input_hash: Mapped[str] = mapped_column(String(64), default="")
    output_hash: Mapped[str] = mapped_column(String(64), default="")
    prompt_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    model_profile: Mapped[str | None] = mapped_column(String(128), nullable=True)
    model_used: Mapped[str | None] = mapped_column(String(128), nullable=True)
    schema_version: Mapped[str] = mapped_column(String(32), default="v1")
    preprocess_version: Mapped[str | None] = mapped_column(String(32), nullable=True)
    status: Mapped[str] = mapped_column(String(32), default="done")
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    diagnostics_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    metrics_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    token_input: Mapped[int | None] = mapped_column(Integer, nullable=True)
    token_output: Mapped[int | None] = mapped_column(Integer, nullable=True)
    duration_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class KbImageSimilarityGroup(Base, TimestampMixin):
    """Visual near-duplicate group for knowledge image assets."""
    __tablename__ = "kb_image_similarity_groups"
    __table_args__ = KB_TABLE_ARGS_EXTEND
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    owner_id: Mapped[int] = mapped_column(Integer, nullable=False)
    representative_asset_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    asset_count: Mapped[int] = mapped_column(Integer, default=0)
    asset_type: Mapped[str] = mapped_column(String(64), default="unknown")
    status: Mapped[str] = mapped_column(String(32), default="active")
    rep_vlm_artifact_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    rep_vlm_cache_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)


class KbImageAsset(Base, TimestampMixin):
    """Fingerprint metadata for an image, page render, screenshot, or poster."""
    __tablename__ = "kb_image_assets"
    __table_args__ = (
        UniqueConstraint(
            "owner_id",
            "document_id",
            "page",
            "hash_schema_version",
            name="uq_kb_image_assets_owner_doc_page_hash_version",
        ),
        KB_TABLE_ARGS_EXTEND,
    )
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    owner_id: Mapped[int] = mapped_column(Integer, nullable=False)
    document_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    file_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    page: Mapped[int | None] = mapped_column(Integer, nullable=True)
    block_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    raw_data_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    asset_type: Mapped[str] = mapped_column(String(64), default="unknown")
    visual_box_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    width: Mapped[int | None] = mapped_column(Integer, nullable=True)
    height: Mapped[int | None] = mapped_column(Integer, nullable=True)
    storage_path: Mapped[str | None] = mapped_column(String(512), nullable=True)
    mime_type: Mapped[str | None] = mapped_column(String(128), nullable=True)
    byte_size: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    file_md5: Mapped[str | None] = mapped_column(String(64), nullable=True)
    ahash: Mapped[str | None] = mapped_column(String(32), nullable=True)
    dhash: Mapped[str | None] = mapped_column(String(32), nullable=True)
    phash: Mapped[str | None] = mapped_column(String(32), nullable=True)
    ocr_text_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    similarity_group_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    group_representative: Mapped[bool] = mapped_column(Boolean, default=False)
    hash_schema_version: Mapped[str] = mapped_column(String(32), default="image_hash_v1")
    clip_model_used: Mapped[str | None] = mapped_column(String(128), nullable=True)
    status: Mapped[str] = mapped_column(String(32), default="active")
    diagnostics_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)


class KbImageSimilarPair(Base, TimestampMixin):
    """Auditable similarity evidence between two image assets."""
    __tablename__ = "kb_image_similar_pairs"
    __table_args__ = (
        UniqueConstraint(
            "source_asset_id",
            "target_asset_id",
            "calc_version",
            name="uq_kb_image_similar_pairs_assets_calc",
        ),
        KB_TABLE_ARGS_EXTEND,
    )
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    owner_id: Mapped[int] = mapped_column(Integer, nullable=False)
    source_asset_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    target_asset_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    hamming_phash: Mapped[int | None] = mapped_column(Integer, nullable=True)
    hamming_dhash: Mapped[int | None] = mapped_column(Integer, nullable=True)
    ocr_text_similarity: Mapped[float | None] = mapped_column(Float, nullable=True)
    clip_cosine: Mapped[float | None] = mapped_column(Float, nullable=True)
    ssim_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    similarity_level: Mapped[str] = mapped_column(String(32), default="suspected")
    decision_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    calc_version: Mapped[str] = mapped_column(String(32), default="image_similarity_v1")
    manual_review: Mapped[bool] = mapped_column(Boolean, default=False)
    review_result: Mapped[str | None] = mapped_column(String(32), nullable=True)


class KbPipelineStale(Base, TimestampMixin):
    """Pipeline stage 产物 hash 记录表。

    每个 stage 完成后记录 artifact hash，用于检测上游变更后标记下游为 stale。
    """
    __tablename__ = "kb_pipeline_stale"
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    document_id: Mapped[int] = mapped_column(BigInteger, nullable=False, index=True)
    stage: Mapped[str] = mapped_column(String(32), nullable=False)
    artifact_hash: Mapped[str] = mapped_column(String(64), default="")
    updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    __table_args__ = (
        UniqueConstraint("document_id", "stage", name="uq_kb_pipeline_stale_doc_stage"),
        KB_TABLE_ARGS_EXTEND,
    )
