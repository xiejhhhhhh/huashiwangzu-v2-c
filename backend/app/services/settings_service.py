from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.models.system import Setting
from app.core.exceptions import NotFound, ConflictError, ValidationError


DEFAULT_SETTINGS: dict[str, str] = {
    "project_name": "华世王镞",
    "system_version": "v2.0.0",
    "login_page_title": "华世王镞管理系统",
    "default_role": "viewer",
}


async def get_all_settings(db: AsyncSession) -> list[Setting]:
    r = await db.execute(select(Setting).order_by(Setting.key))
    return r.scalars().all()


async def get_setting(db: AsyncSession, key: str) -> Setting | None:
    r = await db.execute(select(Setting).where(Setting.key == key))
    return r.scalar_one_or_none()


async def get_setting_value(db: AsyncSession, key: str, default: str = "") -> str:
    s = await get_setting(db, key)
    return s.value if s else default


async def create_setting(db: AsyncSession, key: str, value: str = "", description: str = "") -> Setting:
    existing = await get_setting(db, key)
    if existing:
        raise ConflictError(f"Setting '{key}' already exists")
    s = Setting(key=key, value=value, description=description)
    db.add(s)
    await db.commit()
    await db.refresh(s)
    return s


async def update_setting(db: AsyncSession, key: str, value: str, description: str | None = None) -> Setting:
    s = await get_setting(db, key)
    if not s:
        raise NotFound(f"Setting '{key}' not found")
    s.value = value
    if description is not None:
        s.description = description
    await db.commit()
    await db.refresh(s)
    return s


async def delete_setting(db: AsyncSession, key: str) -> None:
    s = await get_setting(db, key)
    if not s:
        raise NotFound(f"Setting '{key}' not found")
    await db.delete(s)
    await db.commit()


async def get_system_config_map(db: AsyncSession) -> dict[str, str]:
    settings = await get_all_settings(db)
    result = dict(DEFAULT_SETTINGS)
    for s in settings:
        result[s.key] = s.value
    return result


async def update_system_config(db: AsyncSession, updates: dict[str, str]) -> dict[str, str]:
    for key, value in updates.items():
        if not value:
            raise ValidationError(f"'{key}' cannot be empty")
        existing = await get_setting(db, key)
        if existing:
            existing.value = value
        else:
            db.add(Setting(key=key, value=value, description=f"System config: {key}"))
    await db.commit()
    return await get_system_config_map(db)
