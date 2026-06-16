from sqlalchemy import String, Integer, JSON
from sqlalchemy.orm import Mapped, mapped_column
from app.models.base import Base, TimestampMixin


class RoleMatrix(Base, TimestampMixin):
    __tablename__ = "role_matrix"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    role_key: Mapped[str] = mapped_column(String(32), unique=True, nullable=False, comment="admin / editor / viewer")
    display_name: Mapped[str] = mapped_column(String(64), nullable=False, comment="Display name for the role")
    permissions: Mapped[dict] = mapped_column(JSON, nullable=False, comment="Permission map, e.g. {\"user_management\": true, \"system_config\": false}")
