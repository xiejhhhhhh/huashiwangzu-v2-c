from sqlalchemy import String, Integer, ForeignKey, DateTime
from sqlalchemy.orm import Mapped, mapped_column
from datetime import datetime, timezone
from app.models.base import Base, TimestampMixin


class FileShare(Base, TimestampMixin):
    __tablename__ = "framework_file_shares"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    file_id: Mapped[int] = mapped_column(Integer, ForeignKey("framework_file_items.id"), nullable=False)
    shared_by_owner_id: Mapped[int] = mapped_column(Integer, ForeignKey("framework_user_accounts.id"), nullable=False)
    shared_with_user_id: Mapped[int] = mapped_column(Integer, ForeignKey("framework_user_accounts.id"), nullable=False)
    permission: Mapped[str] = mapped_column(String(16), default="read", comment="read | edit")

    def __repr__(self) -> str:
        return f"<FileShare id={self.id} file_id={self.file_id}>"
