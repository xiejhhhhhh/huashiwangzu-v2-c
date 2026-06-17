from datetime import datetime
from sqlalchemy import String, Boolean, Integer, DateTime, BigInteger
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func
from app.models.base import Base, TimestampMixin


class User(Base, TimestampMixin):
    __tablename__ = "framework_user_accounts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    username: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, comment="Login username")
    password_hash: Mapped[str] = mapped_column(String(256), nullable=False, comment="Bcrypt password hash")
    display_name: Mapped[str] = mapped_column(String(128), nullable=False, comment="Display name")
    email: Mapped[str | None] = mapped_column(String(128), nullable=True, comment="Email address")
    role: Mapped[str] = mapped_column(String(32), nullable=False, default="viewer", comment="admin / editor / viewer")
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, comment="Whether account is active")
    last_login: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, comment="Last login time")
    session_version: Mapped[int] = mapped_column(Integer, default=0, comment="Session version for invalidation")

    def __repr__(self) -> str:
        return f"<User id={self.id} username={self.username} role={self.role}>"
