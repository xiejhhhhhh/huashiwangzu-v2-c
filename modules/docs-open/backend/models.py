import hashlib
import logging
import uuid
from datetime import datetime, timezone

from app.models.base import Base
from sqlalchemy import JSON, Boolean, Column, DateTime, Integer, String

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
    hashed = hash_access_token(raw)
    return raw, prefix, hashed


def hash_access_token(raw_token: str) -> str:
    """Hash a raw token for storage/comparison."""
    return hashlib.sha256(raw_token.encode("utf-8")).hexdigest()


def legacy_hash_access_token(raw_token: str) -> str:
    """Hash used by early docs-open tokens; kept until old short-lived tokens expire."""
    return uuid.uuid5(uuid.NAMESPACE_DNS, raw_token).hex
