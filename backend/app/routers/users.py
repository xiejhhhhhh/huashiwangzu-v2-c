from fastapi import APIRouter, Depends
from sqlalchemy import select, or_
from sqlalchemy.ext.asyncio import AsyncSession
from app.database import get_db
from app.schemas.common import ApiResponse
from app.schemas.user import UserResponse, CreateUserRequest, UpdateUserRequest, UserSearchRequest
from app.middleware.auth import get_current_user, require_permission
from app.models.user import User
from app.services.auth import hash_password, create_system_log
from app.core.exceptions import NotFound, ConflictError, ValidationError

router = APIRouter(prefix="/api/users", tags=["users"])

VALID_ROLES = {"viewer", "editor", "admin"}


@router.get("/")
async def list_users(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("admin")),
):
    result = await db.execute(select(User).order_by(User.id))
    users = result.scalars().all()
    return ApiResponse(data=[UserResponse.model_validate(u) for u in users])


@router.get("/search")
async def search_users(
    keyword: str = "",
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("admin")),
):
    query = select(User).order_by(User.id)
    if keyword:
        like = f"%{keyword}%"
        query = query.where(
            or_(User.username.ilike(like), User.display_name.ilike(like), User.email.ilike(like))
        )
    result = await db.execute(query)
    users = result.scalars().all()
    return ApiResponse(data={
        "users": [UserResponse.model_validate(u) for u in users],
        "total": len(users),
        "keyword": keyword,
    })


@router.post("/")
async def create_user(
    body: CreateUserRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("admin")),
):
    if body.role not in VALID_ROLES:
        raise ValidationError(f"Invalid role, must be one of: {', '.join(sorted(VALID_ROLES))}")
    existing = await db.execute(select(User).where(User.username == body.username))
    if existing.scalar_one_or_none():
        raise ConflictError("Username already exists")
    user = User(
        username=body.username,
        password_hash=hash_password(body.password),
        display_name=body.display_name or body.username,
        email=body.email,
        role=body.role,
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)
    await create_system_log(db, "INFO", "users", "create", f"Admin created user [{user.username}]", current_user.id)
    return ApiResponse(data=UserResponse.model_validate(user))


@router.put("/{user_id}")
async def update_user(
    user_id: int,
    body: UpdateUserRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("admin")),
):
    user = await db.get(User, user_id)
    if not user:
        raise NotFound("User not found")
    if body.display_name is not None:
        user.display_name = body.display_name
    if body.email is not None:
        user.email = body.email
    if body.password is not None:
        user.password_hash = hash_password(body.password)
    if body.role is not None:
        if body.role not in VALID_ROLES:
            raise ValidationError(f"Invalid role, must be one of: {', '.join(sorted(VALID_ROLES))}")
        if user_id == current_user.id and body.role != user.role:
            raise ValidationError("Cannot change your own role")
        user.role = body.role
    if body.enabled is not None:
        if user_id == current_user.id and not body.enabled:
            raise ValidationError("Cannot disable yourself")
        user.enabled = body.enabled
    await db.commit()
    await db.refresh(user)
    await create_system_log(db, "INFO", "users", "update", f"Admin updated user [{user.username}]", current_user.id)
    return ApiResponse(data=UserResponse.model_validate(user))


@router.post("/{user_id}/toggle-enabled")
async def toggle_user_enabled(
    user_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("admin")),
):
    if user_id == current_user.id:
        raise ValidationError("Cannot disable yourself")
    user = await db.get(User, user_id)
    if not user:
        raise NotFound("User not found")
    user.enabled = not user.enabled
    await db.commit()
    await db.refresh(user)
    status = "enabled" if user.enabled else "disabled"
    await create_system_log(db, "INFO", "users", "toggle-enabled",
                            f"Admin {status} user [{user.username}]", current_user.id)
    return ApiResponse(data={"message": f"User {status}", "enabled": user.enabled})


@router.get("/roles/list")
async def list_roles(
    current_user: User = Depends(require_permission("admin")),
):
    return ApiResponse(data={
        "roles": [
            {"key": "admin", "name": "管理员"},
            {"key": "editor", "name": "编辑者"},
            {"key": "viewer", "name": "查看者"},
        ]
    })