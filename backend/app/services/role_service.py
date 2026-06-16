import logging
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.models.role_matrix import RoleMatrix
from app.core.exceptions import NotFound, ValidationError

logger = logging.getLogger("v2.role")

DEFAULT_MATRIX = [
    {"role_key": "admin", "display_name": "管理员", "permissions": {"user_management": True, "system_config": True, "role_matrix": True}},
    {"role_key": "editor", "display_name": "编辑者", "permissions": {"user_management": False, "system_config": False, "role_matrix": False}},
    {"role_key": "viewer", "display_name": "查看者", "permissions": {"user_management": False, "system_config": False, "role_matrix": False}},
]

VALID_ROLES = ["admin", "editor", "viewer"]


async def get_role_matrix(db: AsyncSession) -> list[dict]:
    result = await db.execute(select(RoleMatrix).order_by(RoleMatrix.id))
    rows = result.scalars().all()
    if not rows:
        return _seed_default_matrix(db, DEFAULT_MATRIX)
    return [
        {"role_key": r.role_key, "display_name": r.display_name, "permissions": r.permissions}
        for r in rows
    ]


async def update_role_matrix(db: AsyncSession, matrix: list[dict]) -> list[dict]:
    for item in matrix:
        role_key = item.get("role_key", "")
        if role_key not in VALID_ROLES:
            raise ValidationError(f"Invalid role_key: {role_key}, valid: {', '.join(VALID_ROLES)}")

    existing = await db.execute(select(RoleMatrix))
    existing_rows = {r.role_key: r for r in existing.scalars().all()}

    for item in matrix:
        role_key = item["role_key"]
        if role_key in existing_rows:
            row = existing_rows[role_key]
            row.display_name = item.get("display_name", row.display_name)
            row.permissions = item.get("permissions", row.permissions)
        else:
            row = RoleMatrix(role_key=role_key, display_name=item.get("display_name", ""), permissions=item.get("permissions", {}))
            db.add(row)

    await db.commit()

    return await get_role_matrix(db)


async def _seed_default_matrix(db: AsyncSession, defaults: list[dict]) -> list[dict]:
    for item in defaults:
        row = RoleMatrix(role_key=item["role_key"], display_name=item["display_name"], permissions=item["permissions"])
        db.add(row)
    await db.commit()
    return defaults