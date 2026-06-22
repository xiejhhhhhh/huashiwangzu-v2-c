from collections.abc import Iterable
import json
import sys
from importlib import import_module
import importlib.util
import logging
from pathlib import Path

from fastapi import APIRouter, FastAPI

PROJECT_ROOT = Path(__file__).resolve().parents[3]
MODULES_ROOT = PROJECT_ROOT / "modules"
logger = logging.getLogger("v2.module_registry")

_module_load_errors: dict[str, str] = {}

# ── Module metadata for self-healing ──
# Maps: URL prefix (e.g. "/api/codemap") -> module_key (e.g. "codemap")
_module_prefix_map: dict[str, str] = {}
# Maps: module_key -> router_path
_module_router_paths: dict[str, Path] = {}
# Retry throttle: module_key -> last_attempt_timestamp
_retry_last_attempt: dict[str, float] = {}
RETRY_INTERVAL = 5.0  # seconds between retry attempts

PLATFORM_ROUTER_MODULES: tuple[str, ...] = (
    "app.routers.auth",
    "app.routers.desktop",
    "app.routers.files",
    "app.routers.file_transfer",
    "app.routers.file_shares",
    "app.routers.file_create",
    "app.routers.recycle",
    "app.routers.users",
    "app.routers.roles",
    "app.routers.system",
    "app.routers.logs",
    "app.routers.system_status",
    "app.routers.dashboard",
    "app.routers.settings",
    "app.routers.backup",
    "app.routers.tasks",
    "app.routers.notifications",
    "app.routers.feedback",
    "app.routers.office",
    "app.routers.gateway",
    "app.routers.modules",
    "app.routers.office_export",
    "app.routers.editors",
    "app.routers.app_manager",
    "app.routers.menu",
    "app.routers.agent_configs",
)


def _safe_module_router_path(module_dir: Path, router_entry: str) -> Path:
    entry_path = Path(router_entry)
    if entry_path.is_absolute() or ".." in entry_path.parts:
        raise RuntimeError(f"Invalid module router path: {router_entry}")
    router_path = (module_dir / entry_path).resolve()
    if not router_path.is_relative_to(module_dir.resolve()):
        raise RuntimeError(f"Module router path escapes module directory: {router_entry}")
    if not router_path.exists():
        raise RuntimeError(f"Module router file not found: {router_path}")
    return router_path


def iter_module_router_files(modules_root: Path = MODULES_ROOT) -> Iterable[tuple[str, Path]]:
    if not modules_root.exists():
        return
    for manifest_path in sorted(modules_root.glob("*/manifest.json")):
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            logger.error("Skip bad module manifest %s: %s", manifest_path, exc)
            continue
        if manifest.get("enabled") is False:
            continue
        backend_config = manifest.get("backend")
        if not backend_config:
            continue
        if not isinstance(backend_config, dict):
            raise RuntimeError(f"Module backend config must be an object: {manifest_path}")
        if backend_config.get("enabled") is False:
            continue
        router_entry = backend_config.get("router")
        if not router_entry:
            continue
        if not isinstance(router_entry, str):
            raise RuntimeError(f"Module backend.router must be a string: {manifest_path}")
        module_key = str(manifest.get("key") or manifest_path.parent.name)
        yield module_key, _safe_module_router_path(manifest_path.parent, router_entry)


def import_module_router(module_key: str, router_path: Path) -> APIRouter:
    safe_key = module_key.replace("-", "_")
    backend_dir = router_path.parent

    # ── Register the huashiwangzu_modules top-level namespace package ──
    if "huashiwangzu_modules" not in sys.modules:
        import types
        top_pkg = types.ModuleType("huashiwangzu_modules")
        top_pkg.__path__ = []
        sys.modules["huashiwangzu_modules"] = top_pkg

    # ── Register this module's backend as a proper package under the namespace ──
    pkg_name = f"huashiwangzu_modules.{safe_key}"
    if pkg_name not in sys.modules:
        import types
        pkg = types.ModuleType(pkg_name)
        pkg.__path__ = [str(backend_dir)]
        sys.modules[pkg_name] = pkg

    # ── Clear any stale 'backend' module that would pollute namespace for next module ──
    sys.modules.pop("backend", None)

    spec = importlib.util.spec_from_file_location(f"{pkg_name}.router", router_path)
    if not spec or not spec.loader:
        raise RuntimeError(f"Cannot load module router spec: {router_path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    router = getattr(module, "router", None)
    if not isinstance(router, APIRouter):
        raise RuntimeError(f"Module router file must export fastapi.APIRouter named router: {router_path}")
    return router


def get_module_load_errors() -> dict[str, str]:
    return dict(_module_load_errors)


def clear_module_error(module_key: str) -> None:
    """Remove a module from the load error dict after successful self-heal."""
    _module_load_errors.pop(module_key, None)


def clear_all_module_errors() -> None:
    """Clear all module load errors (e.g. on full restart)."""
    _module_load_errors.clear()


def get_module_route_prefix_map() -> dict[str, str]:
    """Return a copy of the prefix→module_key mapping for use by middleware."""
    return dict(_module_prefix_map)


def get_module_router_path(module_key: str) -> Path | None:
    """Return the router file path for a module key, if known."""
    return _module_router_paths.get(module_key)


def build_default_prefix_map() -> None:
    """Build the default prefix→module_key map from manifests before module loading.

    Uses the manifest's ``route_prefix`` field if present, otherwise falls back to
    ``/api/{module_key}`` convention.  After modules are loaded, the actual router
    prefix overrides the guess.
    """
    _module_prefix_map.clear()
    _module_router_paths.clear()

    manifest_dir = PROJECT_ROOT / "modules"
    if not manifest_dir.exists():
        return

    for manifest_path in sorted(manifest_dir.glob("*/manifest.json")):
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            continue
        if manifest.get("enabled") is False:
            continue
        backend_config = manifest.get("backend")
        if not isinstance(backend_config, dict) or backend_config.get("enabled") is False:
            continue
        router_entry = backend_config.get("router")
        if not router_entry:
            continue
        module_key = str(manifest.get("key") or manifest_path.parent.name)

        # Resolve router path
        module_dir = manifest_path.parent.resolve()
        router_path = (module_dir / router_entry).resolve()
        if router_path.exists():
            _module_router_paths[module_key] = router_path

        # Determine prefix: manifest's route_prefix or /api/{key}
        prefix = manifest.get("route_prefix")
        if not prefix:
            prefix = f"/api/{module_key}"
        _module_prefix_map[prefix.rstrip("/")] = module_key


def extract_module_key_from_path(path: str) -> str | None:
    """Given a URL path, return the module key if it matches a known prefix."""
    path = path.rstrip("/")
    for prefix, module_key in sorted(_module_prefix_map.items(), key=lambda x: -len(x[0])):
        if path == prefix or path.startswith(f"{prefix}/"):
            return module_key
    return None


def try_retry_module_router(module_key: str) -> tuple[APIRouter | None, str | None]:
    """Attempt to load / re-load a module's router.

    Returns (router, None) on success or (None, error_message) on failure.
    Caller is responsible for calling ``app.include_router(router)`` on success.
    """
    router_path = _module_router_paths.get(module_key)
    if not router_path:
        return None, f"Module '{module_key}' not found in route map"
    try:
        router = import_module_router(module_key, router_path)
        return router, None
    except Exception as exc:
        logger.error("Retry failed for module '%s': %s", module_key, exc)
        return None, str(exc)


def _normalize_router_prefix(prefix: str) -> str:
    if not prefix:
        return "/"
    return prefix.rstrip("/") or "/"


def _prefixes_overlap(left: str, right: str) -> bool:
    if left == "/" or right == "/":
        return left == right
    return left == right or left.startswith(f"{right}/") or right.startswith(f"{left}/")


def _ensure_prefix_available(prefix: str, module_key: str, seen_prefixes: dict[str, str]) -> None:
    for existing_prefix, owner_module in seen_prefixes.items():
        if _prefixes_overlap(prefix, existing_prefix):
            if prefix == existing_prefix:
                raise RuntimeError(
                    f"Route prefix conflict: module '{module_key}' declares prefix '{prefix}', "
                    f"already claimed by module '{owner_module}'"
                )
            raise RuntimeError(
                f"Route prefix overlap: module '{module_key}' declares prefix '{prefix}', "
                f"overlaps with prefix '{existing_prefix}' from module '{owner_module}'"
            )


def register_module_routers(app: FastAPI, modules_root: Path = MODULES_ROOT) -> None:
    seen_prefixes: dict[str, str] = {}
    _module_load_errors.clear()

    # Build prefix and router path maps from manifests before loading
    build_default_prefix_map()

    for module_key, router_path in iter_module_router_files(modules_root):
        try:
            router = import_module_router(module_key, router_path)
        except Exception as exc:
            _module_load_errors[module_key] = str(exc)
            logger.error("Failed to load module router '%s': %s", module_key, exc)
            continue
        prefix = _normalize_router_prefix(router.prefix)
        _ensure_prefix_available(prefix, module_key, seen_prefixes)
        seen_prefixes[prefix] = module_key
        # Update prefix map with actual router prefix
        _module_prefix_map[prefix] = module_key
        app.include_router(router)
        logger.info("Loaded module router: %s (prefix=%s)", module_key, prefix)


def register_routers(
    app: FastAPI,
    module_paths: Iterable[str] = PLATFORM_ROUTER_MODULES,
    modules_root: Path = MODULES_ROOT,
) -> None:
    for module_path in module_paths:
        module = import_module(module_path)
        app.include_router(module.router)
    register_module_routers(app, modules_root)
