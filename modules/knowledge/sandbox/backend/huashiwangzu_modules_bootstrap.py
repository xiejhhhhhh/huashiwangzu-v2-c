"""Load knowledge router under the same namespace style as the main framework."""
import importlib.util
import sys
import types
from pathlib import Path

from fastapi import APIRouter


def load_knowledge_router(router_path: Path) -> APIRouter:
    backend_dir = router_path.parent
    if "huashiwangzu_modules" not in sys.modules:
        top_pkg = types.ModuleType("huashiwangzu_modules")
        top_pkg.__path__ = []
        sys.modules["huashiwangzu_modules"] = top_pkg

    pkg_name = "huashiwangzu_modules.knowledge"
    if pkg_name not in sys.modules:
        pkg = types.ModuleType(pkg_name)
        pkg.__path__ = [str(backend_dir)]
        sys.modules[pkg_name] = pkg

    spec = importlib.util.spec_from_file_location(f"{pkg_name}.router", router_path)
    if not spec or not spec.loader:
        raise RuntimeError(f"Cannot load router spec: {router_path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    router = getattr(module, "router", None)
    if not isinstance(router, APIRouter):
        raise RuntimeError("Knowledge router must export APIRouter named router")
    return router
