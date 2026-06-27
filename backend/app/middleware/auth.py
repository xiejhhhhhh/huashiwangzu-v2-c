from fastapi import Depends, Request
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.ext.asyncio import AsyncSession
from app.database import get_db
from app.services.auth import decode_access_token, get_user_by_id
from app.models.user import User
from app.core.exceptions import AuthError, PermissionDenied

security = HTTPBearer(auto_error=False)


async def get_current_user(
    request: Request,
    credentials: HTTPAuthorizationCredentials | None = Depends(security),
    db: AsyncSession = Depends(get_db),
) -> User:
    if not credentials:
        raise AuthError("Authentication required")

    payload = decode_access_token(credentials.credentials)
    user_id = int(payload.get("sub", 0))
    token_sv = payload.get("sv", 0)
    user = await get_user_by_id(db, user_id)
    if not user or not user.enabled:
        raise AuthError("User not found or disabled")
    if token_sv != user.session_version:
        raise AuthError("Session expired, please login again")
    return user


def require_permission(min_role: str = "viewer"):
    """Dependency that checks the user's role.
    Role hierarchy: admin > editor > viewer
    """
    role_level = {"admin": 3, "editor": 2, "viewer": 1}

    async def check_role(user: User = Depends(get_current_user)) -> User:
        if role_level.get(user.role, 0) < role_level.get(min_role, 0):
            raise PermissionDenied(
                f"Requires at least '{min_role}' role, got '{user.role}'"
            )
        return user

    return check_role
