from datetime import datetime, timedelta, timezone

from app.core.exceptions import PermissionDenied
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from .models import (
    DocsOpenToken,
    generate_access_token,
    hash_access_token,
    legacy_hash_access_token,
)
from .validators import (
    access_mode_for_mode,
    normalize_client_id,
    normalize_expiry_hours,
    normalize_positive_int,
    normalize_token_scope,
)


async def create_token(
    db: AsyncSession,
    client_id: str,
    open_id: int,
    scope: dict | None = None,
    expiry_hours: int = 2,
) -> dict:
    """Create a new document access token.

    Validates scope.doc_ids against current user's file access.
    Fail-closed: empty scope or non-list doc_ids are rejected.
    Returns dict with client_id, open_id, access_token, scope, expires_at.
    """
    client_id = normalize_client_id(client_id)
    open_id = normalize_positive_int(open_id, "open_id")
    normalized_scope = normalize_token_scope(scope)
    expiry_hours = normalize_expiry_hours(expiry_hours)
    raw, prefix, hashed = generate_access_token()

    token = DocsOpenToken(
        client_id=client_id,
        open_id=open_id,
        access_token_hash=hashed,
        token_prefix=prefix,
        scope=normalized_scope,
        expires_at=datetime.now(timezone.utc) + timedelta(hours=expiry_hours),
    )
    db.add(token)
    await db.commit()
    await db.refresh(token)

    return {
        "client_id": client_id,
        "open_id": str(open_id),
        "access_token": f"{prefix}.{raw}",
        "scope": normalized_scope,
        "expires_at": token.expires_at.isoformat(),
        "token_id": token.id,
    }


async def validate_token(
    db: AsyncSession,
    access_token: str,
    client_id: str,
    open_id: str,
) -> DocsOpenToken:
    """Validate a token. Returns the token record or raises."""
    parts = access_token.split(".", 1)
    if len(parts) != 2:
        raise PermissionDenied("Invalid token format")

    client_id = normalize_client_id(client_id)
    open_id_int = normalize_positive_int(open_id, "open_id")
    prefix, raw = parts
    test_hash = hash_access_token(raw)
    legacy_hash = legacy_hash_access_token(raw)

    result = await db.execute(
        select(DocsOpenToken).where(
            DocsOpenToken.token_prefix == prefix,
            or_(
                DocsOpenToken.access_token_hash == test_hash,
                DocsOpenToken.access_token_hash == legacy_hash,
            ),
            DocsOpenToken.is_revoked.is_(False),
        )
    )
    token = result.scalar_one_or_none()
    if not token:
        raise PermissionDenied("Token not found or revoked")

    if token.client_id != client_id:
        raise PermissionDenied("Client-Id mismatch")

    if token.open_id != open_id_int:
        raise PermissionDenied("Open-Id mismatch")

    expires_at = token.expires_at
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=timezone.utc)
    if expires_at < datetime.now(timezone.utc):
        raise PermissionDenied("Token expired")

    return token


def check_doc_access(token: DocsOpenToken, doc_id: int, mode: str = "read") -> bool:
    """Check if token has access to a specific doc.
    Fail-closed: read allows scope.doc_ids or scope.edit_doc_ids; edit requires
    scope.edit_doc_ids. None/non-list doc_ids or empty scope is rejected.
    """
    try:
        doc_id = normalize_positive_int(doc_id, "doc_id")
        access_mode = access_mode_for_mode(mode)
    except Exception:
        return False

    scope = token.scope or {}
    edit_doc_ids = scope.get("edit_doc_ids")
    if access_mode == "edit":
        return isinstance(edit_doc_ids, list) and doc_id in edit_doc_ids

    doc_ids = scope.get("doc_ids")
    if isinstance(doc_ids, list) and len(doc_ids) > 0:
        return doc_id in doc_ids
    if isinstance(edit_doc_ids, list) and len(edit_doc_ids) > 0:
        return doc_id in edit_doc_ids
    return False
