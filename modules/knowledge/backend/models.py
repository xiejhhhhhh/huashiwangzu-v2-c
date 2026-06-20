"""知识库模块业务表。表名 kb_* 前缀，不加外键到框架表/其他模块表。"""
from datetime import datetime
from sqlalchemy import Boolean, Integer, JSON, String, Text, BigInteger, DateTime, Float
from sqlalchemy.orm import Mapped, mapped_column
from app.models.base import Base, TimestampMixin


class KbCatalog(Base, TimestampMixin):
    """知识库目录树。"""
    __tablename__ = "kb_catalogs"
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    owner_id: Mapped[int] = mapped_column(Integer, nullable=False)
    name: Mapped[str] = mapped_column(String(256), nullable=False)
    parent_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    sort_order: Mapped[int] = mapped_column(Integer, default=0)
    deleted: Mapped[bool] = mapped_column(Boolean, default=False)


class KbDocument(Base, TimestampMixin):
    """知识库文档/资料记录。文件本体走框架文件存储，这里只存逻辑引用。"""
    __tablename__ = "kb_documents"
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
    # 向量化状态：pending/indexing/done/error
    vector_status: Mapped[str] = mapped_column(String(32), default="pending")
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
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    document_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    owner_id: Mapped[int] = mapped_column(Integer, nullable=False)
    page: Mapped[int | None] = mapped_column(Integer, nullable=True)
    chunk_index: Mapped[int] = mapped_column(Integer, default=0)
    block_type: Mapped[str] = mapped_column(String(32), default="段落")  # 段落/标题/表格/图片/代码
    text: Mapped[str] = mapped_column(Text, default="")
    # 向量（JSON 数组存储 1024 维 float，pgvector 可用时切换原生列）
    embedding: Mapped[list | None] = mapped_column(JSON, nullable=True)
    resource_ref: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # 关键词（用于全文检索）
    keywords: Mapped[str | None] = mapped_column(Text, nullable=True)


class KbPageFusion(Base, TimestampMixin):
    """页级融合：同一页的多个块合并为一段连贯文本。"""
    __tablename__ = "kb_page_fusions"
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    document_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    owner_id: Mapped[int] = mapped_column(Integer, nullable=False)
    page: Mapped[int] = mapped_column(Integer, nullable=False)
    fused_text: Mapped[str] = mapped_column(Text, default="")
    # 知识图谱增强后的融合文本
    enhanced_text: Mapped[str | None] = mapped_column(Text, nullable=True)


class KbEntityDictionary(Base, TimestampMixin):
    """实体词典。"""
    __tablename__ = "kb_entity_dictionary"
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
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    owner_id: Mapped[int] = mapped_column(Integer, nullable=False)
    entity_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    alias: Mapped[str] = mapped_column(String(256), nullable=False)


class KbDisambiguation(Base, TimestampMixin):
    """歧义词：同一词形对应多个实体。"""
    __tablename__ = "kb_disambiguation"
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    owner_id: Mapped[int] = mapped_column(Integer, nullable=False)
    term: Mapped[str] = mapped_column(String(256), nullable=False)
    entity_ids: Mapped[list] = mapped_column(JSON, default=list)
    resolved: Mapped[bool] = mapped_column(Boolean, default=False)


class KbGraphNode(Base, TimestampMixin):
    """知识图谱节点。"""
    __tablename__ = "kb_graph_nodes"
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
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    owner_id: Mapped[int] = mapped_column(Integer, nullable=False)
    chunk_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    entity_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    document_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    confidence: Mapped[float] = mapped_column(Float, default=0.0)


class KbEvidence(Base, TimestampMixin):
    """证据：实体在某文档某页的原文依据。"""
    __tablename__ = "kb_evidence"
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
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    owner_id: Mapped[int] = mapped_column(Integer, nullable=False)
    conclusion: Mapped[str] = mapped_column(Text, nullable=False)
    evidence_ids: Mapped[list] = mapped_column(JSON, default=list)
    document_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    confidence: Mapped[float] = mapped_column(Float, default=0.0)


class KbEntityMergeLog(Base, TimestampMixin):
    """实体合并记录。"""
    __tablename__ = "kb_entity_merge_log"
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    owner_id: Mapped[int] = mapped_column(Integer, nullable=False)
    source_entity_ids: Mapped[list] = mapped_column(JSON, default=list)
    target_entity_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    merged_by: Mapped[int] = mapped_column(Integer, nullable=False)
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)


class KbGovernanceCandidate(Base, TimestampMixin):
    """治理候选：待审计/校准的抽取记录。"""
    __tablename__ = "kb_governance_candidates"
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
