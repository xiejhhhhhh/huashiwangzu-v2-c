from sqlalchemy import Integer, BigInteger, JSON
from sqlalchemy.orm import Mapped, mapped_column
from app.models.base import Base, TimestampMixin


class DesktopState(Base, TimestampMixin):
    __tablename__ = "desktop_states"

    user_id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=False, comment="User ID, FK to users.id")
    state_json: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict, comment="Desktop layout / window states JSON")
    version: Mapped[int] = mapped_column(Integer, default=1, comment="Optimistic lock version")

    def __repr__(self) -> str:
        return f"<DesktopState user_id={self.user_id} version={self.version}>"
