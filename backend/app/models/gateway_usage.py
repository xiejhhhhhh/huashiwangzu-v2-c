from datetime import date

from sqlalchemy import BigInteger, Date, Float, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin


class GatewayUsageDaily(Base, TimestampMixin):
    """Daily aggregated model gateway usage costs."""

    __tablename__ = "framework_gateway_usage_daily"
    __table_args__ = (
        UniqueConstraint(
            "usage_date",
            "model_key",
            "provider",
            "module",
            name="uq_framework_gateway_usage_daily_key",
        ),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    usage_date: Mapped[date] = mapped_column(Date, nullable=False)
    model_key: Mapped[str] = mapped_column(String(64), nullable=False)
    provider: Mapped[str] = mapped_column(String(32), default="", nullable=False)
    module: Mapped[str] = mapped_column(String(64), default="", nullable=False)
    call_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    prompt_tokens: Mapped[int] = mapped_column(BigInteger, default=0, nullable=False)
    completion_tokens: Mapped[int] = mapped_column(BigInteger, default=0, nullable=False)
    cost: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
