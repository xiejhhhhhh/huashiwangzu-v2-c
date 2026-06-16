import hashlib
import json
import logging
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.models.app import App
from app.models.user import User

logger = logging.getLogger(__name__)
APPS_MANIFEST = Path(__file__).parent.parent / "seed_data" / "apps.json"


async def list_apps(db: AsyncSession, current_user: User, category: str | None = None):
    query = select(App).where(App.enabled == True)
    if category:
        query = query.where(App.category == category)
    query = query.order_by(App.sort_order)
    result = await db.execute(query)
    apps = result.scalars().all()
    return [app for app in apps if can_user_access_app(app, current_user)]


async def get_app_by_key(db: AsyncSession, key: str):
    result = await db.execute(select(App).where(App.key == key))
    return result.scalar_one_or_none()


async def get_app_by_id(db: AsyncSession, app_id: int):
    result = await db.execute(select(App).where(App.id == app_id))
    return result.scalar_one_or_none()


def can_user_access_app(app: App, current_user: User) -> bool:
    allowed_roles = app.permissions or []
    return not allowed_roles or current_user.role in allowed_roles


async def update_app_enabled(db: AsyncSession, app_id: int, enabled: bool):
    app = await get_app_by_id(db, app_id)
    if not app:
        return None
    app.enabled = enabled
    await db.commit()
    await db.refresh(app)
    return app


async def update_app(db: AsyncSession, app_id: int, data: dict):
    app = await get_app_by_id(db, app_id)
    if not app:
        return None
    for key, value in data.items():
        if hasattr(app, key):
            setattr(app, key, value)
    await db.commit()
    await db.refresh(app)
    return app


async def create_app(db: AsyncSession, data: dict):
    app = App(**data)
    db.add(app)
    await db.commit()
    await db.refresh(app)
    return app


async def sync_apps_from_manifest(db: AsyncSession) -> dict:
    raw = APPS_MANIFEST.read_text(encoding="utf-8")
    rows = json.loads(raw)
    manifest_hash = hashlib.sha256(raw.encode("utf-8")).hexdigest()
    scan_time = datetime.now(timezone.utc)
    created = 0
    updated = 0

    for item in rows:
        app = await get_app_by_key(db, item["key"])
        payload = dict(item)
        payload["manifest_hash"] = manifest_hash
        payload["last_scan_time"] = scan_time
        if app:
            for key, value in payload.items():
                if hasattr(app, key):
                    setattr(app, key, value)
            updated += 1
        else:
            db.add(App(**payload))
            created += 1

    await db.commit()
    return {
        "created": created,
        "updated": updated,
        "total": len(rows),
        "manifest_hash": manifest_hash,
        "last_scan_time": scan_time.isoformat(),
    }


def app_to_dict(app: App) -> dict:
    def _iso(val):
        if val is None:
            return None
        try:
            return val.isoformat()
        except Exception as e:
            logger.warning("Date format fallback: %s", e)
            return str(val)

    return {
        "id": app.id,
        "app_id": app.key,
        "name": app.name,
        "app_type": app.app_type,
        "description": app.description or "",
        "icon": app.icon,
        "category": app.category or "",
        "entry_component_key": app.component_key,
        "route_prefix": app.route_prefix,
        "permissions": app.permissions or [],
        "required_permission": app.required_permission,
        "sort_order": app.sort_order,
        "default_width": app.default_width,
        "default_height": app.default_height,
        "min_width": app.min_width,
        "min_height": app.min_height,
        "singleton": app.singleton,
        "allow_multiple": app.allow_multiple,
        "resizable": app.resizable,
        "window_type": app.window_type,
        "show_on_desktop": app.show_on_desktop,
        "show_in_tray": app.show_in_tray,
        "show_in_launcher": app.show_in_launcher,
        "show_in_sidebar": app.show_in_sidebar,
        "supported_formats": app.supported_formats,
        "editable_formats": app.editable_formats,
        "enabled": app.enabled,
        "needs_frontend_build": app.needs_frontend_build,
        "manifest_hash": app.manifest_hash,
        "last_scan_time": _iso(app.last_scan_time),
        "capabilities": app.capabilities,
        "public_actions": app.public_actions,
        "module_version": app.module_version,
        "contract_version": app.contract_version,
        "installed_version": app.installed_version,
        "framework_min_version": app.framework_min_version,
        "framework_max_version": app.framework_max_version,
        "permission_declaration": app.permission_declaration,
        "db_migration_declaration": app.db_migration_declaration,
        "event_handler_declaration": app.event_handler_declaration,
        "dependency_declaration": app.dependency_declaration,
        "openable_types_declaration": app.openable_types_declaration,
    }
