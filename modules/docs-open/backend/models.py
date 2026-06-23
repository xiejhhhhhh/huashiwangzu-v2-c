import uuid
import logging
from datetime import datetime, timezone
from sqlalchemy import Column, Integer, String, DateTime, Boolean, JSON
from app.models.base import Base

logger = logging.getLogger("v2.docs-open").getChild("models")


class DocsOpenToken(Base):
    __tablename__ = "docs_open_token"

    id = Column(Integer, primary_key=True, autoincrement=True)
    client_id = Column(String(128), nullable=False, index=True)
    open_id = Column(Integer, nullable=False, index=True)
    access_token_hash = Column(String(256), nullable=False, index=True)
    token_prefix = Column(String(8), nullable=False)
    scope = Column(JSON, default=dict)
    expires_at = Column(DateTime(timezone=True), nullable=False)
    is_revoked = Column(Boolean, default=False)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))


def generate_access_token() -> tuple[str, str, str]:
    """Generate a token, return (raw_token, prefix, hashed_token)."""
    raw = uuid.uuid4().hex + uuid.uuid4().hex
    prefix = raw[:8]
    hashed = uuid.uuid5(uuid.NAMESPACE_DNS, raw).hex
    return raw, prefix, hashed
