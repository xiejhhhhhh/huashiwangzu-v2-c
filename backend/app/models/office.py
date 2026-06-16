from sqlalchemy import String, Integer, BigInteger, Text, SmallInteger, ForeignKey, DateTime
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.models.base import Base, TimestampMixin
import datetime


class FileJsonPackage(Base, TimestampMixin):
    __tablename__ = "file_json_packages"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    file_id: Mapped[int] = mapped_column(Integer, ForeignKey("files.id"), nullable=False, comment="关联素材文件ID")
    current_version_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("file_json_versions.id"), nullable=True)
    format_type: Mapped[str] = mapped_column(String(32), default="", comment="格式类型: docx/xlsx/pptx/txt/csv")
    package_status: Mapped[str] = mapped_column(String(32), default="未生成", comment="包状态: 可用/未生成")
    package_path: Mapped[str] = mapped_column(String(512), default="", comment="包存储路径")
    summary: Mapped[str | None] = mapped_column(Text, nullable=True, comment="摘要")
    creator_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), nullable=False)
    deleted_at: Mapped[datetime.datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    versions: Mapped[list["FileJsonVersion"]] = relationship("FileJsonVersion", back_populates="package", foreign_keys="FileJsonVersion.package_id")
    patches: Mapped[list["FileJsonPatch"]] = relationship("FileJsonPatch", back_populates="package", foreign_keys="FileJsonPatch.package_id")

    def __repr__(self) -> str:
        return f"<FileJsonPackage id={self.id} file_id={self.file_id}>"


class FileJsonVersion(Base, TimestampMixin):
    __tablename__ = "file_json_versions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    package_id: Mapped[int] = mapped_column(Integer, ForeignKey("file_json_packages.id"), nullable=False)
    version_number: Mapped[int] = mapped_column(Integer, default=1, comment="版本号，自增")
    json_content: Mapped[str] = mapped_column(Text, default="", comment="JSON内容全文")
    summary: Mapped[str | None] = mapped_column(Text, nullable=True, comment="版本摘要")
    creator_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), nullable=False)

    package: Mapped[FileJsonPackage] = relationship("FileJsonPackage", back_populates="versions", foreign_keys=[package_id])

    __table_args__ = {"extend_existing": True}

    def __repr__(self) -> str:
        return f"<FileJsonVersion id={self.id} v{self.version_number}>"


class FileJsonPatch(Base, TimestampMixin):
    __tablename__ = "file_json_patches"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    package_id: Mapped[int] = mapped_column(Integer, ForeignKey("file_json_packages.id"), nullable=False)
    source_version_id: Mapped[int] = mapped_column(Integer, ForeignKey("file_json_versions.id"), nullable=False)
    target_version_id: Mapped[int] = mapped_column(Integer, ForeignKey("file_json_versions.id"), nullable=False)
    operation_type: Mapped[str] = mapped_column(String(64), default="replace_text", comment="操作类型: replace_text/modify_cell/insert_image")
    json_path: Mapped[str] = mapped_column(String(512), default="", comment="定位路径")
    before_summary: Mapped[str | None] = mapped_column(Text, nullable=True, comment="修改前摘要")
    after_content: Mapped[str] = mapped_column(Text, default="", comment="修改后内容")
    risk_level: Mapped[str] = mapped_column(String(16), default="medium", comment="风险等级: low/medium/high")
    reason: Mapped[str | None] = mapped_column(Text, nullable=True, comment="修改原因")
    patch_status: Mapped[str] = mapped_column(String(32), default="已应用", comment="补丁状态: 已应用/待审核/已拒绝")
    creator_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), nullable=False)

    package: Mapped[FileJsonPackage] = relationship("FileJsonPackage", back_populates="patches", foreign_keys=[package_id])

    def __repr__(self) -> str:
        return f"<FileJsonPatch id={self.id} op={self.operation_type}>"


class FileJsonTask(Base, TimestampMixin):
    __tablename__ = "file_json_tasks"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    file_id: Mapped[int] = mapped_column(Integer, ForeignKey("files.id"), nullable=False)
    package_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("file_json_packages.id"), nullable=True)
    task_type: Mapped[str] = mapped_column(String(64), default="", comment="任务类型")
    status: Mapped[str] = mapped_column(String(32), default="pending", comment="任务状态")
    progress: Mapped[int] = mapped_column(SmallInteger, default=0, comment="进度 0-100")
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True, comment="错误信息")
    creator_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), nullable=False)

    def __repr__(self) -> str:
        return f"<FileJsonTask id={self.id} type={self.task_type}>"
