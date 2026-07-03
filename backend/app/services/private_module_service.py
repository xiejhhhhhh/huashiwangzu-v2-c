import hashlib
import json
import logging
import shutil
from pathlib import Path

from fastapi import Depends, FastAPI
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import AppException, ConflictError, NotFound, PermissionDenied, ValidationError
from app.middleware.auth import require_permission
from app.models.private_module import PrivateModule
from app.models.user import User
from app.routers.registry import (
    _module_load_errors,
    _module_prefix_map,
    _module_router_paths,
    import_module_router,
)
from app.services.module_registry import (
    _current_capability_snapshot,
    _restore_capability_snapshot,
    private_capability_registration,
    unregister_capability,
)

logger = logging.getLogger(__name__)

WORKSPACES_ROOT = Path(__file__).resolve().parents[3] / "data" / "workspaces"
PRIVATE_MODULES_INSTALL_ROOT = Path(__file__).resolve().parents[3] / "data" / "private_modules"

_APP_INSTANCE: FastAPI | None = None
# Tracks capability keys registered by each private module.
# Key: f"__private__{owner_id}__{module_key}" -> list of capability keys
_PRIVATE_MODULE_CAP_KEYS: dict[str, list[str]] = {}


def set_app_instance(app: FastAPI) -> None:
    global _APP_INSTANCE
    _APP_INSTANCE = app


def get_app_instance() -> FastAPI:
    if _APP_INSTANCE is None:
        raise RuntimeError("FastAPI app instance not set. Call set_app_instance during startup.")
    return _APP_INSTANCE


def _unregister_capability_keys(capability_keys: list[str]) -> None:
    for cap_key in capability_keys:
        module_part, action_part = cap_key.split(":", 1)
        unregister_capability(module_part, action_part)


def _registered_private_capability_keys(owner_id: int, snapshot: dict[str, dict]) -> list[str]:
    current = _current_capability_snapshot()
    return sorted(
        key
        for key, entry in current.items()
        if entry.get("owner_id") == owner_id and snapshot.get(key) != entry
    )


def _workspace_private_modules_dir(owner_id: int) -> Path:
    return WORKSPACES_ROOT / str(owner_id) / "private_modules"


def _workspace_private_packs_dir(owner_id: int) -> Path:
    return WORKSPACES_ROOT / str(owner_id) / "private_packs"


def _install_dir(owner_id: int) -> Path:
    d = PRIVATE_MODULES_INSTALL_ROOT / str(owner_id)
    d.mkdir(parents=True, exist_ok=True)
    return d


def _compute_checksum(manifest: dict) -> str:
    raw = json.dumps(manifest, ensure_ascii=False, sort_keys=True)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _safe_private_router_path(module_dir: Path, router_entry: str) -> Path:
    entry_path = Path(router_entry)
    if entry_path.is_absolute() or ".." in entry_path.parts:
        raise ValidationError(f"Invalid private module router path: {router_entry}")
    router_path = (module_dir / entry_path).resolve()
    if not router_path.is_relative_to(module_dir.resolve()):
        raise ValidationError(f"Private module router path escapes module directory: {router_entry}")
    if not router_path.exists():
        raise NotFound(f"Private module router not found: {router_entry}")
    return router_path


def _private_access_dependency(owner_id: int, private_key: str, prefix: str):
    async def _require_private_access(user: User = Depends(require_permission("viewer"))) -> User:
        if _module_prefix_map.get(prefix.rstrip("/")) != private_key:
            raise NotFound("Private module is not active")
        if user.id != owner_id and user.role != "admin":
            raise PermissionDenied("Permission denied")
        return user

    return _require_private_access


def _refresh_middleware_stack(app: FastAPI) -> None:
    # Dynamic include/remove happens after the ASGI stack may already be built.
    # Rebuild it so runtime routing matches the registry and DB lifecycle state.
    app.middleware_stack = app.build_middleware_stack()


async def preview_private_module(
    db: AsyncSession, owner_id: int, module_key: str, module_type: str = "module"
) -> dict:
    modules_dir = (
        _workspace_private_modules_dir(owner_id)
        if module_type == "module"
        else _workspace_private_packs_dir(owner_id)
    )
    module_dir = modules_dir / module_key
    manifest_path = module_dir / "manifest.json"

    if not manifest_path.exists():
        raise NotFound(
            f"Private {module_type} '{module_key}' not found in workspace"
        )

    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        raise ValidationError(f"Invalid manifest: {exc}")

    checksum = _compute_checksum(manifest)
    return {
        "module_key": module_key,
        "module_type": module_type,
        "name": manifest.get("name", module_key),
        "version": manifest.get("module_version", "1.0.0"),
        "description": manifest.get("description", ""),
        "icon": manifest.get("icon", "Collection"),
        "has_backend": bool(
            isinstance(manifest.get("backend"), dict)
            and manifest["backend"].get("router")
        ),
        "has_frontend": bool(
            manifest.get("component_key")
            and (module_dir / "frontend" / manifest["component_key"]).exists()
        ),
        "checksum": checksum,
        "public_actions": manifest.get("public_actions", {}),
        "workspace_path": str(module_dir),
    }


async def install_private_module(
    db: AsyncSession, owner_id: int, module_key: str, module_type: str = "module"
) -> dict:
    # Preview first to validate manifest
    preview = await preview_private_module(db, owner_id, module_key, module_type)
    modules_dir = (
        _workspace_private_modules_dir(owner_id)
        if module_type == "module"
        else _workspace_private_packs_dir(owner_id)
    )
    source_dir = modules_dir / module_key

    existing = await _get_private_module(db, owner_id, module_key)
    if existing:
        raise ConflictError(
            f"Private module '{module_key}' already installed (status={existing.status})"
        )

    target_dir = _install_dir(owner_id) / module_key
    if target_dir.exists():
        shutil.rmtree(str(target_dir))

    shutil.copytree(str(source_dir), str(target_dir), dirs_exist_ok=True)
    manifest_path = target_dir / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    checksum = _compute_checksum(manifest)

    record = PrivateModule(
        owner_id=owner_id,
        module_key=module_key,
        name=preview["name"],
        module_type=module_type,
        version=preview["version"],
        status="installed",
        checksum=checksum,
        manifest_json=manifest,
        source_path=str(source_dir),
        installed_path=str(target_dir),
    )
    db.add(record)
    await db.commit()
    await db.refresh(record)

    return _record_to_dict(record)


async def activate_private_module(
    db: AsyncSession, owner_id: int, module_key: str
) -> dict:
    record = await _get_active_or_installed(db, owner_id, module_key)
    module_dir = Path(record.installed_path)
    manifest = record.manifest_json if isinstance(record.manifest_json, dict) else {}

    if record.status == "active":
        return _record_to_dict(record)

    record.lkg_checksum = record.checksum
    record.lkg_version = record.version

    registered_prefix = ""
    private_key = f"__private__{owner_id}__{module_key}"
    cap_snapshot_before = _current_capability_snapshot()
    try:
        backend_config = manifest.get("backend")
        if isinstance(backend_config, dict) and backend_config.get("router"):
            router_entry = backend_config["router"]
            router_path = _safe_private_router_path(module_dir, router_entry)
            with private_capability_registration(owner_id):
                router = import_module_router(private_key, router_path)
            prefix = _normalize_private_prefix(owner_id, module_key, manifest)
            registered_prefix = prefix
            _module_prefix_map[prefix.rstrip("/")] = private_key
            _module_router_paths[private_key] = router_path
            record.router_prefix = prefix

            app = get_app_instance()
            app.include_router(
                router,
                prefix=prefix,
                dependencies=[Depends(_private_access_dependency(owner_id, private_key, prefix))],
            )
            _refresh_middleware_stack(app)
            logger.info("Registered private module router: %s at %s", module_key, prefix)

        registered_keys = _registered_private_capability_keys(owner_id, cap_snapshot_before)
        if registered_keys:
            _PRIVATE_MODULE_CAP_KEYS[private_key] = registered_keys

        record.status = "active"
        record.error_message = None
    except Exception as exc:
        if registered_prefix:
            _unregister_private_module(owner_id, module_key, registered_prefix)
        _restore_capability_snapshot(cap_snapshot_before)
        _PRIVATE_MODULE_CAP_KEYS.pop(private_key, None)
        record.status = "failed"
        record.error_message = str(exc)
        logger.error("Failed to activate private module '%s': %s", module_key, exc)
        await db.commit()
        await db.refresh(record)
        return _record_to_dict(record)

    await db.commit()
    await db.refresh(record)
    return _record_to_dict(record)


async def deactivate_private_module(
    db: AsyncSession, owner_id: int, module_key: str
) -> dict:
    record = await _get_private_module(db, owner_id, module_key)
    if not record:
        raise NotFound(f"Private module '{module_key}' not found")
    if record.status != "active":
        return _record_to_dict(record)

    router_prefix = record.router_prefix
    try:
        _unregister_private_module(owner_id, module_key, router_prefix)
    except Exception as exc:
        logger.error("Failed to unregister private module '%s' runtime: %s", module_key, exc)
        raise AppException(f"Failed to deactivate private module: {exc}", status_code=500)

    record.status = "installed"
    await db.commit()
    await db.refresh(record)
    return _record_to_dict(record)


async def uninstall_private_module(
    db: AsyncSession, owner_id: int, module_key: str
) -> dict:
    record = await _get_private_module(db, owner_id, module_key)
    if not record:
        raise NotFound(f"Private module '{module_key}' not found")

    if record.status == "active":
        _unregister_private_module(owner_id, module_key, record.router_prefix)

    module_dir = Path(record.installed_path)
    if module_dir.exists():
        shutil.rmtree(str(module_dir))

    await db.delete(record)
    await db.commit()
    return {"module_key": module_key, "status": "uninstalled"}


async def rollback_private_module(
    db: AsyncSession, owner_id: int, module_key: str
) -> dict:
    record = await _get_private_module(db, owner_id, module_key)
    if not record:
        raise NotFound(f"Private module '{module_key}' not found")
    if not record.lkg_checksum:
        raise ValidationError("No last-known-good version to roll back to")

    if record.status == "active":
        _unregister_private_module(owner_id, module_key, record.router_prefix)

    record.checksum = record.lkg_checksum
    record.version = record.lkg_version or record.version
    record.status = "rolled_back"
    await db.commit()

    try:
        return await activate_private_module(db, owner_id, module_key)
    except Exception as exc:
        await db.refresh(record)
        record.status = "failed"
        record.error_message = f"Rollback activation failed: {exc}"
        await db.commit()
        await db.refresh(record)
        return _record_to_dict(record)


async def list_private_modules(
    db: AsyncSession, owner_id: int
) -> list[dict]:
    result = await db.execute(
        select(PrivateModule)
        .where(PrivateModule.owner_id == owner_id)
        .order_by(PrivateModule.module_key)
    )
    return [_record_to_dict(r) for r in result.scalars().all()]


async def list_workspace_private_modules(
    owner_id: int, module_type: str = "module"
) -> list[dict]:
    modules_dir = (
        _workspace_private_modules_dir(owner_id)
        if module_type == "module"
        else _workspace_private_packs_dir(owner_id)
    )
    if not modules_dir.exists():
        return []

    results = []
    for module_dir in sorted(modules_dir.iterdir()):
        if not module_dir.is_dir() or module_dir.name.startswith(("_", ".")):
            continue
        manifest_path = module_dir / "manifest.json"
        if not manifest_path.exists():
            continue
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            results.append({
                "module_key": module_dir.name,
                "module_type": module_type,
                "name": manifest.get("name", module_dir.name),
                "version": manifest.get("module_version", "1.0.0"),
                "description": manifest.get("description", ""),
                "icon": manifest.get("icon", "Collection"),
            })
        except (json.JSONDecodeError, OSError):
            continue
    return results


# ── Internal helpers ──


async def _get_private_module(
    db: AsyncSession, owner_id: int, module_key: str
) -> PrivateModule | None:
    result = await db.execute(
        select(PrivateModule).where(
            PrivateModule.owner_id == owner_id,
            PrivateModule.module_key == module_key,
        )
    )
    return result.scalar_one_or_none()


async def _get_active_or_installed(
    db: AsyncSession, owner_id: int, module_key: str
) -> PrivateModule:
    record = await _get_private_module(db, owner_id, module_key)
    if not record:
        raise NotFound(
            f"Private module '{module_key}' not installed. Preview and install first."
        )
    return record


def _unregister_private_module(owner_id: int, module_key: str, router_prefix: str | None = None) -> None:
    private_key = f"__private__{owner_id}__{module_key}"
    prefix = router_prefix.rstrip("/") if router_prefix else ""
    if not prefix:
        prefix = next((k for k, v in _module_prefix_map.items() if v == private_key), "")
    if prefix:
        _module_prefix_map.pop(prefix, None)
        try:
            app = get_app_instance()
            app.router.routes[:] = [
                route for route in app.router.routes
                if not _route_belongs_to_private_prefix(getattr(route, "path", ""), prefix)
            ]
            _refresh_middleware_stack(app)
        except RuntimeError:
            logger.warning("FastAPI app unavailable while unregistering private module %s", private_key)
    _module_router_paths.pop(private_key, None)
    _module_load_errors.pop(private_key, None)
    # Clean up capabilities registered by this private module during activation
    tracked_keys = _PRIVATE_MODULE_CAP_KEYS.pop(private_key, None)
    if tracked_keys:
        _unregister_capability_keys(tracked_keys)


def _route_belongs_to_private_prefix(path: str, prefix: str) -> bool:
    normalized = prefix.rstrip("/")
    return path == normalized or path.startswith(f"{normalized}/")


def _normalize_private_prefix(owner_id: int, module_key: str, manifest: dict) -> str:
    manifest_prefix = manifest.get("route_prefix", "")
    if manifest_prefix:
        return f"/api/private/{owner_id}{manifest_prefix}"
    return f"/api/private/{owner_id}/{module_key}"


def _record_to_dict(record: PrivateModule) -> dict:
    return {
        "id": record.id,
        "owner_id": record.owner_id,
        "module_key": record.module_key,
        "name": record.name,
        "module_type": record.module_type,
        "version": record.version,
        "status": record.status,
        "checksum": record.checksum,
        "lkg_checksum": record.lkg_checksum,
        "lkg_version": record.lkg_version,
        "router_prefix": record.router_prefix,
        "error_message": record.error_message,
        "created_at": record.created_at.isoformat() if record.created_at else None,
        "updated_at": record.updated_at.isoformat() if record.updated_at else None,
    }
