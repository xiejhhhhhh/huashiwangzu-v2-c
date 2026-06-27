from sqlalchemy import String, Integer, Text, JSON, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column
from app.models.base import Base, TimestampMixin


class PrivateModule(Base, TimestampMixin):
    __tablename__ = "framework_private_modules"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    owner_id: Mapped[int] = mapped_column(
        Integer, nullable=False, index=True, comment="User who owns this module"
    )
    module_key: Mapped[str] = mapped_column(
        String(128), nullable=False, comment="Module identifier key"
    )
    name: Mapped[str] = mapped_column(
        String(256), nullable=False, default="", comment="Display name"
    )
    module_type: Mapped[str] = mapped_column(
        String(32), default="module", comment="module | pack"
    )
    version: Mapped[str] = mapped_column(
        String(32), default="1.0.0", comment="Current version"
    )
    status: Mapped[str] = mapped_column(
        String(32), default="installed",
        comment="previewed | installed | active | rolled_back | failed"
    )
    checksum: Mapped[str] = mapped_column(
        String(64), default="", comment="SHA256 of installed manifest"
    )
    lkg_checksum: Mapped[str | None] = mapped_column(
        String(64), nullable=True, comment="Last known good checksum"
    )
    lkg_version: Mapped[str | None] = mapped_column(
        String(32), nullable=True, comment="Last known good version"
    )
    manifest_json: Mapped[dict] = mapped_column(
        JSON, default=dict, comment="Parsed manifest content"
    )
    source_path: Mapped[str] = mapped_column(
        String(512), default="", comment="Original workspace path"
    )
    installed_path: Mapped[str] = mapped_column(
        String(512), default="", comment="Managed install path"
    )
    router_prefix: Mapped[str] = mapped_column(
        String(255), default="", comment="Registered API prefix"
    )
    error_message: Mapped[str | None] = mapped_column(
        Text, nullable=True, comment="Last error message"
    )

    __table_args__ = (
        UniqueConstraint("owner_id", "module_key",
                         name="uq_private_module_per_owner"),
    )

    def __repr__(self) -> str:
        return f"<PrivateModule id={self.id} owner={self.owner_id} key={self.module_key} status={self.status}>"
