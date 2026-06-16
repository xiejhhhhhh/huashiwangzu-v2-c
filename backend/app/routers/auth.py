import logging
from datetime import datetime, timezone
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from app.database import get_db
from app.schemas.auth import LoginRequest, LoginResponse, UserInfo
from app.schemas.common import ApiResponse
from app.services.auth import authenticate, create_access_token, clear_login_rate_limit, create_system_log
from app.middleware.auth import get_current_user
from app.models.user import User

logger = logging.getLogger("v2.auth")

router = APIRouter(prefix="/api", tags=["auth"])


@router.post("/login")
async def login(body: LoginRequest, db: AsyncSession = Depends(get_db)):
    logger.info(f"Login attempt: username='{body.username}'")
    user = await authenticate(db, body.username, body.password)

    # Increment session_version to invalidate old tokens
    user.session_version += 1
    user.last_login = datetime.now(timezone.utc)
    await db.commit()
    await db.refresh(user)

    clear_login_rate_limit(body.username)

    token = create_access_token(user.id, user.role, user.session_version)
    logger.info(f"Login success: id={user.id} role={user.role}")

    await create_system_log(db, "INFO", "auth", "login", f"User [{user.username}] logged in", user.id)

    return ApiResponse(data=LoginResponse(
        access_token=token,
        user=UserInfo(
            id=user.id,
            username=user.username,
            display_name=user.display_name,
            email=user.email,
            role=user.role,
        ),
    ))


@router.post("/logout")
async def logout(current_user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    await create_system_log(db, "INFO", "auth", "logout", f"User [{current_user.username}] logged out", current_user.id)
    return ApiResponse(data={"message": "Logged out"})


@router.get("/current-user")
async def current_user(current_user: User = Depends(get_current_user)):
    return ApiResponse(data=UserInfo(
        id=current_user.id,
        username=current_user.username,
        display_name=current_user.display_name,
        email=current_user.email,
        role=current_user.role,
    ))