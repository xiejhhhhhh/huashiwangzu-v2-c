"""内容运行时新增表(方案07 §19.3-B 冻结)。

- framework_file_revisions:     File 的不可变字节血缘,上传/替换/投影只新增 Revision
- framework_ingestion_runs:     预处理运行账本,终态不原地重开,replay 建 generation+1
- framework_event_deliveries:   事件 per-handler 投递账本,至少一次投递+幂等
- framework_content_edit_leases: 每 Package 最多一个有效编辑租约(乐观锁配套)
- framework_resource_analyses:  资源分析结果(OCR/VLM/ASR)按输入+模型版本不可变

本轮(§24)越过 VLM/ASR:resource_analyses 表建好,但不批量回填模型产出。
"""
from datetime import datetime, timezone

from sqlalchemy import (
    BigInteger, DateTime, ForeignKey, Index, Integer, String, Text, UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


def _now() -> datetime:
    return datetime.now(timezone.utc)


class FileRevision(Base):
    """framework_file_revisions —— File 的某一时刻真实字节。唯一键 (file_id, revision_no)。"""
    __tablename__ = "framework_file_revisions"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    file_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("framework_file_items.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    revision_no: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    storage_path: Mapped[str] = mapped_column(String(1024), nullable=False, default="")
    size: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    sha256: Mapped[str | None] = mapped_column(String(64), nullable=True, comment="原始字节 SHA-256")
    mime_type: Mapped[str] = mapped_column(String(128), nullable=False, default="application/octet-stream")
    # user_import | projection | external_replace (§19.4)
    origin: Mapped[str] = mapped_column(String(32), nullable=False, default="user_import")
    created_by: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)

    __table_args__ = (
        UniqueConstraint("file_id", "revision_no", name="uq_file_revision_no"),
        Index("idx_file_revision_file", "file_id"),
        Index("idx_file_revision_sha", "sha256"),
    )


class IngestionRun(Base):
    """framework_ingestion_runs —— 预处理运行账本。唯一键 (source_revision_id, pipeline_version, generation)。"""
    __tablename__ = "framework_ingestion_runs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, comment="UUIDv7")
    file_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    source_revision_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True, index=True)
    owner_id: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    source_sha256: Mapped[str | None] = mapped_column(String(64), nullable=True)
    pipeline_version: Mapped[str] = mapped_column(String(32), nullable=False, default="v1")
    generation: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    package_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    package_version_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    # queued|running|waiting_retry|paused|cancelling|completed|degraded|failed|dead_letter|cancelled
    status: Mapped[str] = mapped_column(String(24), nullable=False, default="queued", index=True)
    trigger: Mapped[str] = mapped_column(String(32), nullable=False, default="upload")
    requested_by: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    replay_of_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    cancel_requested: Mapped[bool] = mapped_column(default=False)
    cancel_reason: Mapped[str | None] = mapped_column(String(256), nullable=True)
    error_code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    lock_version: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, onupdate=_now)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    __table_args__ = (
        UniqueConstraint(
            "source_revision_id", "pipeline_version", "generation",
            name="uq_ingestion_source_pipeline_gen",
        ),
        Index("idx_ingestion_file", "file_id"),
        Index("idx_ingestion_status", "status"),
    )


class EventDelivery(Base):
    """framework_event_deliveries —— 事件 per-handler 投递账本。唯一键 (event_id, handler_key, handler_version)。"""
    __tablename__ = "framework_event_deliveries"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    event_id: Mapped[int] = mapped_column(BigInteger, nullable=False, index=True)
    handler_key: Mapped[str] = mapped_column(String(128), nullable=False)
    handler_version: Mapped[str] = mapped_column(String(32), nullable=False, default="v1")
    status: Mapped[str] = mapped_column(String(24), nullable=False, default="pending")
    attempt_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    max_attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=5)
    lease_token: Mapped[str | None] = mapped_column(String(64), nullable=True)
    lease_owner: Mapped[str | None] = mapped_column(String(128), nullable=True)
    lease_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    retry_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, onupdate=_now)

    __table_args__ = (
        UniqueConstraint(
            "event_id", "handler_key", "handler_version",
            name="uq_event_delivery_handler",
        ),
        Index("idx_event_delivery_event", "event_id"),
    )


class ContentEditLease(Base):
    """framework_content_edit_leases —— 每 Package 最多一个有效编辑租约。"""
    __tablename__ = "framework_content_edit_leases"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    package_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    base_version_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    token_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    holder_id: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=_now)
    revision: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, onupdate=_now)

    __table_args__ = (
        # 每个 Package 最多一个有效租约:用部分唯一索引在迁移里落地(active 判定含 expires_at)。
        Index("idx_edit_lease_package", "package_id"),
    )


class ResourceAnalysis(Base):
    """framework_resource_analyses —— 资源分析结果(OCR/VLM/ASR),按输入+模型版本不可变。

    替代 framework_resources 上原地更新的 ocr_text/vlm_metadata。本轮(§24)越过模型调用,
    表建好但不批量回填。
    """
    __tablename__ = "framework_resource_analyses"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    resource_id: Mapped[int] = mapped_column(BigInteger, nullable=False, index=True)
    analysis_type: Mapped[str] = mapped_column(String(32), nullable=False, comment="ocr|vlm|asr|...")
    model: Mapped[str] = mapped_column(String(128), nullable=False, default="")
    model_version: Mapped[str] = mapped_column(String(64), nullable=False, default="")
    input_sha256: Mapped[str | None] = mapped_column(String(64), nullable=True)
    output_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    # succeeded|failed|skipped(reason=model_budget_deferred)
    status: Mapped[str] = mapped_column(String(24), nullable=False, default="succeeded")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, onupdate=_now)

    __table_args__ = (
        UniqueConstraint(
            "resource_id", "analysis_type", "model_version", "input_sha256",
            name="uq_resource_analysis_input",
        ),
        Index("idx_resource_analysis_resource", "resource_id"),
    )

