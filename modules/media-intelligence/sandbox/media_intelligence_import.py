from __future__ import annotations

import importlib.util
import os
import sys
import types
from pathlib import Path


def load_pipeline() -> types.ModuleType:
    return _load_backend_module("pipeline")


def load_router() -> types.ModuleType:
    return _load_backend_module("router")


def _load_backend_module(module_name: str) -> types.ModuleType:
    os.environ.setdefault("JWT_SECRET", "media-intelligence-sandbox")
    module_root = Path(__file__).resolve().parents[1]
    package_name = "media_intelligence_backend"
    package = types.ModuleType(package_name)
    package.__path__ = [str(module_root / "backend")]
    sys.modules.setdefault(package_name, package)

    providers_name = f"{package_name}.providers"
    providers = types.ModuleType(providers_name)
    providers.__path__ = [str(module_root / "backend" / "providers")]
    sys.modules.setdefault(providers_name, providers)

    module_path = module_root / "backend" / f"{module_name}.py"
    spec = importlib.util.spec_from_file_location(f"{package_name}.{module_name}", module_path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Cannot load media-intelligence {module_name} module")
    module = importlib.util.module_from_spec(spec)
    sys.modules[f"{package_name}.{module_name}"] = module
    spec.loader.exec_module(module)
    return module
