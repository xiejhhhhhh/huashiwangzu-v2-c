"""Content edit lease —— 每 Package 最多一个有效租约（方案07 §19.6）。

token 只在签发时明文返回一次；库内只存 sha256(token)。
"""
from __future__ import annotations

import hashlib
import secrets
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ConflictError, NotFound, PermissionDenied, ValidationError
from app.models.content import ContentPackage
from app.models.content_runtime import ContentEditLease


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


async def _get_package(db: AsyncSession, package_id: int) -> ContentPackage:
    pkg = await db.get(ContentPackage, package_id)
    if pkg is None or pkg.deleted:
        raise NotFound(f"Package {package_id} not found")
    return pkg


async def acquire_lease(
    db: AsyncSession,
    *,
    package_id: int,
    holder_id: int,
    base_version_id: int | None = None,
    ttl_seconds: int = 300,
) -> dict:
    pkg = await _get_package(db, package_id)
    now = _now()
    ttl = max(30, min(int(ttl_seconds or 300), 3600))

    existing = await db.scalar(
        select(ContentEditLease)
        .where(
            ContentEditLease.package_id == package_id,
            ContentEditLease.expires_at > now,
        )
        .order_by(ContentEditLease.id.desc())
        .limit(1)
    )
    if existing is not None and existing.holder_id != holder_id:
        raise ConflictError("Edit lease held by another user")

    token = secrets.token_urlsafe(24)
    token_hash = _hash_token(token)
    expires = now + timedelta(seconds=ttl)

    if existing is not None and existing.holder_id == holder_id:
        existing.token_hash = token_hash
        existing.base_version_id = base_version_id or pkg.current_version_id
        existing.expires_at = expires
        existing.revision = int(existing.revision or 0) + 1
        lease = existing
    else:
        lease = ContentEditLease(
            package_id=package_id,
            base_version_id=base_version_id or pkg.current_version_id,
            token_hash=token_hash,
            holder_id=holder_id,
            expires_at=expires,
            revision=1,
        )
        db.add(lease)

    await db.commit()
    await db.refresh(lease)
    return {
        "packageId": package_id,
        "token": token,
        "expiresAt": lease.expires_at.isoformat() if lease.expires_at else None,
        "baseVersionId": lease.base_version_id,
        "revision": lease.revision,
        "holderId": lease.holder_id,
    }


async def renew_lease(
    db: AsyncSession,
    *,
    package_id: int,
    holder_id: int,
    token: str,
    ttl_seconds: int = 300,
) -> dict:
    await _get_package(db, package_id)
    if not token:
        raise ValidationError("lock token required")
    now = _now()
    token_hash = _hash_token(token)
    lease = await db.scalar(
        select(ContentEditLease)
        .where(
            ContentEditLease.package_id == package_id,
            ContentEditLease.token_hash == token_hash,
        )
        .order_by(ContentEditLease.id.desc())
        .limit(1)
    )
    if lease is None:
        raise NotFound("Lease not found")
    if lease.holder_id != holder_id:
        raise PermissionDenied("Lease holder mismatch")
    if lease.expires_at and lease.expires_at <= now:
        raise ConflictError("Lease expired")

    ttl = max(30, min(int(ttl_seconds or 300), 3600))
    lease.expires_at = now + timedelta(seconds=ttl)
    lease.revision = int(lease.revision or 0) + 1
    await db.commit()
    await db.refresh(lease)
    return {
        "packageId": package_id,
        "expiresAt": lease.expires_at.isoformat() if lease.expires_at else None,
        "baseVersionId": lease.base_version_id,
        "revision": lease.revision,
        "holderId": lease.holder_id,
        "renewed": True,
    }


async def release_lease(
    db: AsyncSession,
    *,
    package_id: int,
    holder_id: int,
    token: str,
) -> dict:
    await _get_package(db, package_id)
    token_hash = _hash_token(token)
    lease = await db.scalar(
        select(ContentEditLease)
        .where(
            ContentEditLease.package_id == package_id,
            ContentEditLease.token_hash == token_hash,
        )
        .order_by(ContentEditLease.id.desc())
        .limit(1)
    )
    if lease is None:
        raise NotFound("Lease not found")
    if lease.holder_id != holder_id:
        raise PermissionDenied("Lease holder mismatch")
    # 立即过期 = 释放
    lease.expires_at = _now()
    lease.revision = int(lease.revision or 0) + 1
    await db.commit()
    return {"packageId": package_id, "released": True}


async def assert_lease(
    db: AsyncSession,
    *,
    package_id: int,
    holder_id: int,
    token: str | None,
) -> ContentEditLease | None:
    """写路径可选校验：有 token 则必须有效；无 token 返回 None（只读/自动保存宽松模式）。"""
    if not token:
        return None
    now = _now()
    token_hash = _hash_token(token)
    lease = await db.scalar(
        select(ContentEditLease)
        .where(
            ContentEditLease.package_id == package_id,
            ContentEditLease.token_hash == token_hash,
        )
        .order_by(ContentEditLease.id.desc())
        .limit(1)
    )
    if lease is None:
        raise ConflictError("Invalid lock token")
    if lease.holder_id != holder_id:
        raise PermissionDenied("Lease holder mismatch")
    if lease.expires_at and lease.expires_at <= now:
        raise ConflictError("Lease expired")
    return lease
