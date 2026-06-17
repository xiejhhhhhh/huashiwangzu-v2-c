from sqlalchemy import String, Boolean, Integer, BigInteger, Text, ForeignKey, DateTime
from sqlalchemy.orm import Mapped, mapped_column, relationship
from datetime import datetime, timezone
from app.models.base import Base, TimestampMixin


class Folder(Base, TimestampMixin):
    __tablename__ = "framework_file_folders"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(256), nullable=False, comment="Folder name")
    parent_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("framework_file_folders.id", ondelete="CASCADE"), nullable=True, comment="Parent folder id, null=root"
    )
    owner_id: Mapped[int] = mapped_column(Integer, ForeignKey("framework_user_accounts.id"), nullable=False, comment="Creator")
    deleted: Mapped[bool] = mapped_column(Boolean, default=False, comment="Soft delete flag")
    deleted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, comment="Time when soft deleted"
    )

    children: Mapped[list["Folder"]] = relationship("Folder", backref="parent", remote_side="Folder.id", passive_deletes=True)

    def __repr__(self) -> str:
        return f"<Folder id={self.id} name={self.name}>"


class File(Base, TimestampMixin):
    __tablename__ = "framework_file_items"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(256), nullable=False, comment="File name without extension")
    extension: Mapped[str] = mapped_column(String(32), default="", comment="File extension, e.g. txt, pdf")
    size: Mapped[int] = mapped_column(BigInteger, default=0, comment="File size in bytes")
    folder_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("framework_file_folders.id", ondelete="SET NULL"), nullable=True, comment="Parent folder"
    )
    owner_id: Mapped[int] = mapped_column(Integer, ForeignKey("framework_user_accounts.id"), nullable=False)
    storage_path: Mapped[str] = mapped_column(String(512), default="", comment="Path on disk relative to storage root")
    mime_type: Mapped[str] = mapped_column(String(128), default="", comment="MIME type")
    md5_hash: Mapped[str | None] = mapped_column(String(32), nullable=True, comment="MD5 hash")
    ref_count: Mapped[int] = mapped_column(Integer, default=1, comment="Reference count for content dedup")
    deleted: Mapped[bool] = mapped_column(Boolean, default=False, comment="Soft delete flag")
    deleted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, comment="Time when soft deleted"
    )

    def __repr__(self) -> str:
        return f"<File id={self.id} name={self.name}.{self.extension}>"
