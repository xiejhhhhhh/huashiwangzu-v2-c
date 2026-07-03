"""Authentication and authorization for docs-open module."""

from __future__ import annotations

import os

from app.core.exceptions import AuthError, PermissionDenied
from app.database import get_db
from app.models.user import User
from app.services.auth import decode_access_token
from app.services.auth import get_user_by_id as auth_get_user
from fastapi import Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession


async def get_authenticated_user(
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> User:
    """Authenticate via token triple (X- headers) or JWT bearer.

    Token triple (仿腾讯文档三件套) takes precedence when all three
    X-Client-Id, X-Open-Id, X-Access-Token are present.
    Falls back to standard JWT Bearer token (Authorization header).
    """
    from ..token_service import validate_token

    x_client_id = request.headers.get("X-Client-Id")
    x_open_id = request.headers.get("X-Open-Id")
    x_access_token = request.headers.get("X-Access-Token")

    if x_client_id and x_open_id and x_access_token:
        token_record = await validate_token(db, x_access_token, x_client_id, x_open_id)
        user = await db.get(User, token_record.open_id)
        if not user or not user.enabled:
            raise PermissionDenied("User not found or disabled")
        return user

    auth_header = request.headers.get("Authorization", "")
    if auth_header.startswith("Bearer "):
        jwt_token = auth_header[7:]
        payload = decode_access_token(jwt_token)
        user_id = int(payload.get("sub", 0))
        token_sv = payload.get("sv", 0)
        user = await auth_get_user(db, user_id)
        if not user or not user.enabled:
            raise PermissionDenied("User not found or disabled")
        if token_sv != user.session_version:
            raise PermissionDenied("Session expired, please login again")
        return user

    raise AuthError("Authentication required")


async def get_bearer_authenticated_user(
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> User:
    """Authenticate only via framework JWT bearer token."""
    auth_header = request.headers.get("Authorization", "")
    if not auth_header.startswith("Bearer "):
        raise AuthError("Authentication required")

    jwt_token = auth_header[7:]

    payload = decode_access_token(jwt_token)
    user_id = int(payload.get("sub", 0))
    token_sv = payload.get("sv", 0)
    user = await auth_get_user(db, user_id)
    if not user or not user.enabled:
        raise PermissionDenied("User not found or disabled")
    if token_sv != user.session_version:
        raise PermissionDenied("Session expired, please login again")
    return user


def require_docs_permission(min_role: str = "viewer", allow_scoped_token: bool = False):
    """Dependency factory: auth + role check for docs-open endpoints."""
    role_level = {"admin": 3, "editor": 2, "viewer": 1}

    async def _check(
        request: Request,
        db: AsyncSession = Depends(get_db),
    ) -> User:
        user = (
            await get_authenticated_user(request, db)
            if allow_scoped_token
            else await get_bearer_authenticated_user(request, db)
        )
        if role_level.get(user.role, 0) < role_level.get(min_role, 0):
            raise PermissionDenied(
                f"Requires at least '{min_role}' role, got '{user.role}'"
            )
        return user

    return _check


def _get_base_url(request: Request) -> str:
    """Build a trusted base URL without honoring client-controlled forwarded headers."""
    configured = os.environ.get("DOCS_OPEN_BASE_URL", "").strip()
    if configured:
        return configured.rstrip("/")
    return f"{request.url.scheme}://{request.url.netloc}".rstrip("/")
