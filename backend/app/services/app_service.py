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
MODULES_ROOT = Path(__file__).resolve().parents[3] / "modules"
WORKSPACES_ROOT = Path(__file__).resolve().parents[3] / "data" / "workspaces"


async def list_apps(db: AsyncSession, current_user: User, category: str | None = None):
    query = select(App).where(App.enabled)
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


def _read_platform_app_manifests() -> list[dict]:
    raw = APPS_MANIFEST.read_text(encoding="utf-8")
    return json.loads(raw)


def _module_manifest_to_app_payload(module_dir: Path, manifest: dict) -> dict:
    module_key = str(manifest.get("key") or module_dir.name)
    backend_config = manifest.get("backend") if isinstance(manifest.get("backend"), dict) else {}
    route_prefix = manifest.get("route_prefix") or backend_config.get("route_prefix") or ""
    raw_component_key = str(manifest.get("component_key") or "index.vue")
    window_type = manifest.get("window_type") or "normal"
    if window_type == "background-service" or not (module_dir / "frontend" / raw_component_key).exists():
        component_key = ""
    else:
        component_key = f"{module_dir.name}/{raw_component_key}"
    return {
        "key": module_key,
        "name": manifest.get("name") or module_key,
        "icon": manifest.get("icon") or "Collection",
        "category": manifest.get("category") or "",
        "component_key": component_key,
        "route_prefix": route_prefix,
        "permissions": manifest.get("permissions") or [],
        "sort_order": manifest.get("sort_order") or 200,
        "default_width": manifest.get("default_width") or 900,
        "default_height": manifest.get("default_height") or 600,
        "min_width": manifest.get("min_width") or 400,
        "min_height": manifest.get("min_height") or 300,
        "singleton": manifest.get("singleton", True),
        "allow_multiple": manifest.get("allow_multiple", False),
        "window_type": manifest.get("window_type") or "normal",
        "show_on_desktop": manifest.get("show_on_desktop", False),
        "show_in_tray": manifest.get("show_in_tray", False),
        "show_in_launcher": manifest.get("show_in_launcher", True),
        "show_in_sidebar": manifest.get("show_in_sidebar", False),
        "enabled": manifest.get("enabled", True),
        "module_version": manifest.get("module_version") or "1.0.0",
        "contract_version": manifest.get("contract_version") or "2.0",
        "capabilities": manifest.get("capabilities"),
        "public_actions": manifest.get("public_actions"),
        "permission_declaration": manifest.get("permission_declaration"),
        "db_migration_declaration": manifest.get("db_migration_declaration"),
        "event_handler_declaration": manifest.get("event_handler_declaration"),
        "dependency_declaration": manifest.get("dependency_declaration"),
        "openable_types_declaration": manifest.get("openable_types_declaration"),
        "supported_formats": manifest.get("supported_formats"),
        "editable_formats": manifest.get("editable_formats"),
        "creatable_formats": manifest.get("creatable_formats"),
    }


def _read_module_app_manifests(modules_root: Path = MODULES_ROOT) -> list[dict]:
    if not modules_root.exists():
        return []
    rows: list[dict] = []
    for manifest_path in sorted(modules_root.glob("*/manifest.json")):
        module_dir = manifest_path.parent
        if module_dir.name.startswith(("_", ".")):
            continue
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            if manifest.get("enabled") is False:
                continue
            rows.append(_module_manifest_to_app_payload(module_dir, manifest))
        except Exception as exc:
            logger.error("Skip bad module manifest %s: %s", manifest_path, exc)
            continue
    return rows


def _read_private_module_app_manifests(
    owner_id: int | None = None
) -> list[dict]:
    rows: list[dict] = []
    base = WORKSPACES_ROOT
    if not base.exists():
        return rows

    user_dirs = [base / str(owner_id)] if owner_id else sorted(base.iterdir())
    for user_dir in user_dirs:
        if not user_dir.is_dir() or not user_dir.name.isdigit():
            continue
        uid = int(user_dir.name)
        pm_dir = user_dir / "private_modules"
        if not pm_dir.exists():
            continue
        for module_dir in sorted(pm_dir.iterdir()):
            if not module_dir.is_dir() or module_dir.name.startswith(("_", ".")):
                continue
            manifest_path = module_dir / "manifest.json"
            if not manifest_path.exists():
                continue
            try:
                manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
                if manifest.get("enabled") is False:
                    continue
                payload = _module_manifest_to_app_payload(module_dir, manifest)
                payload["key"] = f"__private__{uid}__{module_dir.name}"
                payload["app_type"] = "private"
                payload["required_permission"] = f"private:{uid}"
                rows.append(payload)
            except Exception as exc:
                logger.error("Skip bad private module manifest %s: %s", manifest_path, exc)
                continue
    return rows


def load_app_manifests(modules_root: Path = MODULES_ROOT) -> list[dict]:
    return [
        *_read_platform_app_manifests(),
        *_read_module_app_manifests(modules_root),
        *_read_private_module_app_manifests(),
    ]


async def sync_apps_from_manifest(db: AsyncSession) -> dict:
    rows = load_app_manifests()
    manifest_hash = hashlib.sha256(
        json.dumps(rows, ensure_ascii=False, sort_keys=True).encode("utf-8")
    ).hexdigest()
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

    # 孤儿清理：DB 里存在但 manifest 已删除的 app，一并删除
    manifest_keys = {item["key"] for item in rows}
    existing_result = await db.execute(select(App))
    deleted = 0
    for existing_app in existing_result.scalars().all():
        if existing_app.key not in manifest_keys:
            await db.delete(existing_app)
            deleted += 1

    await db.commit()
    return {
        "created": created,
        "updated": updated,
        "deleted": deleted,
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
        "creatable_formats": app.creatable_formats,
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
