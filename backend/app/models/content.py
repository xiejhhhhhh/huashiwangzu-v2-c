"""Content package lifecycle models.

framework_content_packages — structured content canonical source
framework_content_package_versions — content snapshots at version boundaries
framework_resources — content-addressed resource store (images, media, etc.)
framework_resource_refs — resource-to-package/block/version bindings
"""
from datetime import datetime, timezone

from sqlalchemy import JSON, BigInteger, Boolean, DateTime, ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class ContentPackage(Base):
    __tablename__ = "framework_content_packages"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    owner_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True, comment="Owner user id")
    source_file_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("framework_file_items.id", ondelete="SET NULL"),
        nullable=True, index=True, comment="Source physical file record"
    )
    package_type: Mapped[str] = mapped_column(
        String(32), nullable=False, default="generic",
        comment="document / spreadsheet / presentation / pdf / image / text / generic"
    )
    origin_type: Mapped[str] = mapped_column(
        String(32), default="uploaded",
        comment="uploaded / generated / manual / imported"
    )
    source_extension: Mapped[str] = mapped_column(String(32), default="", comment="Original file extension")
    package_version: Mapped[str] = mapped_column(String(16), default="1.0", comment="Content IR schema version")
    manifest_json: Mapped[str | None] = mapped_column(Text, nullable=True, comment="Package-level manifest metadata")
    current_version_id: Mapped[int | None] = mapped_column(Integer, nullable=True, comment="Current active version id")
    status: Mapped[str] = mapped_column(
        String(16), default="parsed",
        comment="pending / parsed / failed / stale"
    )
    parse_error: Mapped[str | None] = mapped_column(Text, nullable=True, comment="Last parse error message")
    source_hash: Mapped[str | None] = mapped_column(String(64), nullable=True, comment="SHA-256 of source file at parse time")
    # WP1（方案07 §19.3-C）扩张期新列：Profile / schema 版本 / 来源 Revision / 活跃 Ingestion
    profile: Mapped[str | None] = mapped_column(String(32), nullable=True, comment="document/spreadsheet/presentation/pdf/media/generic")
    schema_version: Mapped[str | None] = mapped_column(String(64), nullable=True, comment="内容 IR schema 版本，如 canonical-content-ir/v1")
    source_revision_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True, comment="来源 FileRevision id（血缘事实源）")
    active_ingestion_id: Mapped[str | None] = mapped_column(String(36), nullable=True, comment="当前活跃 IngestionRun id(UUIDv7)")
    deleted: Mapped[bool] = mapped_column(Boolean, default=False, comment="Soft delete flag")
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc)
    )

    __table_args__ = (
        Index("idx_cp_owner_status", "owner_id", "status"),
        Index("idx_cp_source_file", "source_file_id"),
    )


class ContentPackageVersion(Base):
    __tablename__ = "framework_content_package_versions"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    package_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("framework_content_packages.id", ondelete="CASCADE"),
        nullable=False, index=True
    )
    version_no: Mapped[int] = mapped_column(Integer, nullable=False, default=1, comment="Monotonic version number")
    content_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}", comment="Blocks + document structure (no binary resources)")
    # WP1 §19.3-C 扩张期新增字段（DB 已由 patcher 建列，此处补 ORM 映射）
    parent_version_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True, comment="Parent version (同 Package、版本号更小)")
    schema_version: Mapped[str | None] = mapped_column(String(64), nullable=True, comment="内容 IR schema 版本，如 canonical-content-ir/v1")
    profile: Mapped[str | None] = mapped_column(String(32), nullable=True, comment="document/spreadsheet/presentation/pdf/media/generic")
    content_sha256: Mapped[str | None] = mapped_column(String(64), nullable=True, comment="canonical IR 的 RFC8785 规范化 SHA-256")
    source_sha256: Mapped[str | None] = mapped_column(String(64), nullable=True, comment="原始字节 SHA-256")
    fidelity_level: Mapped[str | None] = mapped_column(String(16), nullable=True, comment="lossless/structural/textual/metadata_only")
    retention_state: Mapped[str] = mapped_column(String(16), default="active", comment="active/superseded/gc_pending")
    # WP3 双写：CanonicalContentIRV1 载荷（旧 content_json 兼容期不动）
    canonical_json: Mapped[str | None] = mapped_column(Text, nullable=True, comment="CanonicalContentIRV1 JSON（Content Runtime 主结构）")
    summary: Mapped[str | None] = mapped_column(String(512), nullable=True, comment="Human-readable version summary")
    operation_type: Mapped[str] = mapped_column(
        String(32), default="parse",
        comment="parse / update / replace / append / restore / export"
    )
    operation_meta_json: Mapped[str | None] = mapped_column(Text, nullable=True, comment="Additional operation metadata")
    created_by: Mapped[int] = mapped_column(Integer, nullable=False, default=0, comment="User who created this version")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )

    __table_args__ = (
        Index("idx_cpv_pkg_version", "package_id", "version_no", unique=True),
    )


class Resource(Base):
    __tablename__ = "framework_resources"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    owner_id: Mapped[int] = mapped_column(Integer, nullable=False, default=0, comment="Creator/owner user id")
    hash: Mapped[str] = mapped_column(String(64), nullable=False, unique=True, comment="Content hash (default sha256)")
    hash_algorithm: Mapped[str] = mapped_column(String(16), default="sha256", comment="Hash algorithm used")
    resource_type: Mapped[str] = mapped_column(
        String(32), nullable=False,
        comment="image / audio / video / binary / document / rendered_page"
    )
    mime_type: Mapped[str] = mapped_column(String(128), default="application/octet-stream")
    storage_path: Mapped[str] = mapped_column(String(1024), nullable=False, comment="Content-addressed storage path")
    file_size: Mapped[int] = mapped_column(BigInteger, default=0)
    width: Mapped[int | None] = mapped_column(Integer, nullable=True, comment="Image/video width in px")
    height: Mapped[int | None] = mapped_column(Integer, nullable=True, comment="Image/video height in px")
    duration_ms: Mapped[int | None] = mapped_column(Integer, nullable=True, comment="Audio/video duration")
    description: Mapped[str | None] = mapped_column(Text, nullable=True, comment="VLM-generated visual description")
    ocr_text: Mapped[str | None] = mapped_column(Text, nullable=True, comment="OCR-extracted text")
    vlm_metadata: Mapped[str | None] = mapped_column(JSON, nullable=True, comment="VLM understanding result")
    ref_count: Mapped[int] = mapped_column(Integer, nullable=False, default=1, comment="Number of references to this resource")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc)
    )

    __table_args__ = (
        Index("idx_res_hash", "hash"),
    )


class ResourceRef(Base):
    __tablename__ = "framework_resource_refs"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    package_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("framework_content_packages.id", ondelete="CASCADE"),
        nullable=False, index=True
    )
    version_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("framework_content_package_versions.id", ondelete="SET NULL"),
        nullable=True, comment="Version that introduced this ref"
    )
    resource_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("framework_resources.id", ondelete="CASCADE"),
        nullable=False, comment="Referenced resource"
    )
    block_id: Mapped[str | None] = mapped_column(String(64), nullable=True, comment="Stable block id within package content_json")
    usage_type: Mapped[str] = mapped_column(
        String(32), default="embedded",
        comment="embedded / referenced / thumbnail / rendered_page"
    )
    page: Mapped[int | None] = mapped_column(Integer, nullable=True, comment="Page / slide number (1-indexed)")
    coordinates: Mapped[str | None] = mapped_column(JSON, nullable=True, comment="Bounding box / position in document")
    usage_hints: Mapped[str | None] = mapped_column(Text, nullable=True, comment="Description of how resource is used")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )

    __table_args__ = (
        Index("idx_rr_pkg_resource", "package_id", "resource_id", unique=True),
        Index("idx_rr_pkg_block", "package_id", "block_id"),
    )
