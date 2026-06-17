from collections.abc import Iterable
import json
from importlib import import_module
import importlib.util
import logging
from pathlib import Path

from fastapi import APIRouter, FastAPI

PROJECT_ROOT = Path(__file__).resolve().parents[3]
MODULES_ROOT = PROJECT_ROOT / "modules"
logger = logging.getLogger("v2.module_registry")

_module_load_errors: dict[str, str] = {}

PLATFORM_ROUTER_MODULES: tuple[str, ...] = (
    "app.routers.auth",
    "app.routers.desktop",
    "app.routers.files",
    "app.routers.file_transfer",
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
    "app.routers.office_export",
    "app.routers.editors",
    "app.routers.app_manager",
    "app.routers.menu",
    "app.routers.agent_session",
    "app.routers.agent_tools",
    "app.routers.agent_prompts",
    "app.routers.agent_prompt_actions",
    "app.routers.image_vision",
    "app.routers.knowledge",
    "app.routers.knowledge_aggregation",
    "app.routers.knowledge_analysis_results",
    "app.routers.knowledge_entity_merge",
    "app.routers.knowledge_dictionary",
    "app.routers.knowledge_evaluation",
    "app.routers.knowledge_evidence_write",
    "app.routers.knowledge_governance",
    "app.routers.knowledge_governance_write",
    "app.routers.knowledge_graph",
    "app.routers.knowledge_labels",
    "app.routers.knowledge_tasks",
    "app.routers.knowledge_visual_resources",
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
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
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
    spec = importlib.util.spec_from_file_location(f"huashiwangzu_modules.{safe_key}.router", router_path)
    if not spec or not spec.loader:
        raise RuntimeError(f"Cannot load module router spec: {router_path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    router = getattr(module, "router", None)
    if not isinstance(router, APIRouter):
        raise RuntimeError(f"Module router file must export fastapi.APIRouter named router: {router_path}")
    return router


def get_module_load_errors() -> dict[str, str]:
    return dict(_module_load_errors)


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
