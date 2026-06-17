import json
from pathlib import Path

from app.services.app_service import load_app_manifests


def test_load_app_manifests_includes_platform_and_module_entries(tmp_path: Path) -> None:
    backend_root = tmp_path / "backend" / "app" / "seed_data"
    backend_root.mkdir(parents=True)
    (backend_root / "apps.json").write_text(
        json.dumps([
            {
                "key": "core-system",
                "name": "System Core",
                "icon": "Setting",
                "component_key": "apps/core-system/index.vue",
                "route_prefix": "/api/system",
            }
        ]),
        encoding="utf-8",
    )

    modules_root = tmp_path / "modules"
    module_dir = modules_root / "demo-module"
    module_dir.mkdir(parents=True)
    (module_dir / "manifest.json").write_text(
        json.dumps({
            "key": "demo-module",
            "name": "Demo Module",
            "icon": "Collection",
            "component_key": "index.vue",
            "route_prefix": "/api/demo-module",
        }),
        encoding="utf-8",
    )

    import app.services.app_service as app_service

    original_apps_manifest = app_service.APPS_MANIFEST
    original_modules_root = app_service.MODULES_ROOT
    try:
        app_service.APPS_MANIFEST = backend_root / "apps.json"
        app_service.MODULES_ROOT = modules_root
        rows = load_app_manifests(modules_root)
    finally:
        app_service.APPS_MANIFEST = original_apps_manifest
        app_service.MODULES_ROOT = original_modules_root

    assert [row["key"] for row in rows] == ["core-system", "demo-module"]
    assert rows[1]["component_key"] == "demo-module/index.vue"
    assert rows[1]["route_prefix"] == "/api/demo-module"
