import json
from pathlib import Path

from fastapi import FastAPI

from app.routers.registry import (
    get_module_load_errors,
    iter_module_router_files,
    register_module_routers,
    register_routers,
)


def test_module_router_files_are_loaded_from_manifest(tmp_path: Path) -> None:
    module_dir = tmp_path / "sample-module"
    module_dir.mkdir()
    router_file = module_dir / "backend_router.py"
    router_file.write_text(
        "from fastapi import APIRouter\n"
        "router = APIRouter(prefix='/api/sample-module', tags=['sample-module'])\n"
        "@router.get('/ping')\n"
        "async def ping():\n"
        "    return {'ok': True}\n",
        encoding="utf-8",
    )
    (module_dir / "manifest.json").write_text(
        json.dumps({
            "key": "sample-module",
            "backend": {"router": "backend_router.py"},
        }),
        encoding="utf-8",
    )

    app = FastAPI()
    register_routers(app, module_paths=(), modules_root=tmp_path)

    assert "/api/sample-module/ping" in app.openapi()["paths"]


def test_module_manifest_without_backend_router_is_not_mounted(tmp_path: Path) -> None:
    module_dir = tmp_path / "frontend-only"
    module_dir.mkdir()
    (module_dir / "manifest.json").write_text(
        json.dumps({"key": "frontend-only", "component_key": "index.vue"}),
        encoding="utf-8",
    )

    assert list(iter_module_router_files(tmp_path)) == []


def test_backend_enabled_false_skips_module_router(tmp_path: Path) -> None:
    module_dir = tmp_path / "backend-disabled"
    module_dir.mkdir()
    router_file = module_dir / "backend_router.py"
    router_file.write_text(
        "from fastapi import APIRouter\n"
        "router = APIRouter(prefix='/api/backend-disabled')\n",
        encoding="utf-8",
    )
    (module_dir / "manifest.json").write_text(
        json.dumps({
            "key": "backend-disabled",
            "backend": {"enabled": False, "router": "backend_router.py"},
        }),
        encoding="utf-8",
    )

    assert list(iter_module_router_files(tmp_path)) == []


def test_module_router_prefix_conflict_fails_fast(tmp_path: Path) -> None:
    for module_key in ("sample-module-a", "sample-module-a-copy"):
        module_dir = tmp_path / module_key
        module_dir.mkdir()
        (module_dir / "backend_router.py").write_text(
            "from fastapi import APIRouter\n"
            "router = APIRouter(prefix='/api/sample-module-a')\n",
            encoding="utf-8",
        )
        (module_dir / "manifest.json").write_text(
            json.dumps({
                "key": module_key,
                "backend": {"router": "backend_router.py"},
            }),
            encoding="utf-8",
        )

    app = FastAPI()
    try:
        register_module_routers(app, modules_root=tmp_path)
    except RuntimeError as exc:
        assert "Route prefix conflict" in str(exc)
    else:
        raise AssertionError("Expected prefix conflict to fail fast")


def test_module_router_prefix_overlap_fails_fast(tmp_path: Path) -> None:
    modules = {
        "sample-module-b": "/api/sample-module-b",
        "sample-module-b-v2": "/api/sample-module-b/v2",
    }
    for module_key, prefix in modules.items():
        module_dir = tmp_path / module_key
        module_dir.mkdir()
        (module_dir / "backend_router.py").write_text(
            "from fastapi import APIRouter\n"
            f"router = APIRouter(prefix='{prefix}')\n",
            encoding="utf-8",
        )
        (module_dir / "manifest.json").write_text(
            json.dumps({
                "key": module_key,
                "backend": {"router": "backend_router.py"},
            }),
            encoding="utf-8",
        )

    app = FastAPI()
    try:
        register_module_routers(app, modules_root=tmp_path)
    except RuntimeError as exc:
        assert "Route prefix overlap" in str(exc)
    else:
        raise AssertionError("Expected prefix overlap to fail fast")


def test_module_router_import_failure_is_recorded_and_skipped(tmp_path: Path) -> None:
    good_dir = tmp_path / "good-module"
    good_dir.mkdir()
    (good_dir / "backend_router.py").write_text(
        "from fastapi import APIRouter\n"
        "router = APIRouter(prefix='/api/good-module')\n"
        "@router.get('/ping')\n"
        "async def ping():\n"
        "    return {'ok': True}\n",
        encoding="utf-8",
    )
    (good_dir / "manifest.json").write_text(
        json.dumps({"key": "good-module", "backend": {"router": "backend_router.py"}}),
        encoding="utf-8",
    )

    broken_dir = tmp_path / "broken-module"
    broken_dir.mkdir()
    (broken_dir / "backend_router.py").write_text(
        "import missing_dependency_for_registry_test\n",
        encoding="utf-8",
    )
    (broken_dir / "manifest.json").write_text(
        json.dumps({"key": "broken-module", "backend": {"router": "backend_router.py"}}),
        encoding="utf-8",
    )

    app = FastAPI()
    register_module_routers(app, modules_root=tmp_path)

    assert "/api/good-module/ping" in app.openapi()["paths"]
    assert "broken-module" in get_module_load_errors()
