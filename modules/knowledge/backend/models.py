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


class KbPipelineRun(Base, TimestampMixin):
    """一次知识库全链路运行的持久诊断账本。"""
    __tablename__ = "kb_pipeline_runs"
    __table_args__ = KB_TABLE_ARGS_EXTEND
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    document_id: Mapped[int] = mapped_column(BigInteger, nullable=False, index=True)
    owner_id: Mapped[int] = mapped_column(Integer, nullable=False)
    file_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    task_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    trigger: Mapped[str] = mapped_column(String(64), default="kb_pipeline")
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
