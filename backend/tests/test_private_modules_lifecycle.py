"""Private module lifecycle must match its router state."""

import shutil
from pathlib import Path
from uuid import uuid4

import pytest
from app.core.exceptions import PermissionDenied
from app.database import AsyncSessionLocal
from app.main import app
from app.models.private_module import PrivateModule
from app.services import private_module_service as pms
from app.services.module_registry import (
    _current_capability_keys,
    _current_capability_snapshot,
    call_capability,
    list_capabilities,
)
from httpx import ASGITransport, AsyncClient
from sqlalchemy import delete

SEED_PASS = "admin123"


async def _login(client: AsyncClient) -> tuple[str, int]:
    resp = await client.post("/api/login", json={"username": "admin", "password": SEED_PASS})
    data = resp.json()["data"]
    return data["access_token"], data["user"]["id"]


async def _cleanup_private_module(owner_id: int, module_key: str, data_root: Path) -> None:
    pms._unregister_private_module(owner_id, module_key, f"/api/private/{owner_id}/probe-private")
    async with AsyncSessionLocal() as db:
        await db.execute(delete(PrivateModule).where(PrivateModule.module_key == module_key))
        await db.commit()
    shutil.rmtree(data_root, ignore_errors=True)


def _write_private_module(
    root: Path,
    owner_id: int,
    module_key: str,
    *,
    register_capability: bool = False,
    capability_module_key: str | None = None,
    capability_action: str = "probe",
) -> None:
    module_dir = root / "workspaces" / str(owner_id) / "private_modules" / module_key
    backend_dir = module_dir / "backend"
    backend_dir.mkdir(parents=True, exist_ok=True)
    (module_dir / "manifest.json").write_text(
        (
            "{"
            f"\"key\":\"{module_key}\","
            f"\"name\":\"{module_key}\","
            "\"module_version\":\"1.0.0\","
            "\"route_prefix\":\"/probe-private\","
            "\"backend\":{\"enabled\":true,\"router\":\"backend/router.py\"}"
            "}"
        ),
        encoding="utf-8",
    )
    capability_code = ""
    if register_capability:
        cap_module = capability_module_key or module_key
        capability_code = (
            "from app.services.module_registry import register_capability\n"
            "async def capability_handler(params, caller):\n"
            "    return {'success': True, 'data': {'caller': caller}}\n"
            f"register_capability('{cap_module}', '{capability_action}', capability_handler)\n"
        )
    (backend_dir / "router.py").write_text(
        (
            "from fastapi import APIRouter\n"
            f"{capability_code}"
            "router = APIRouter()\n"
            "@router.get('/ping')\n"
            "async def ping():\n"
            "    return {'ok': True}\n"
        ),
        encoding="utf-8",
    )


@pytest.mark.asyncio
async def test_private_module_deactivate_removes_runtime_route(monkeypatch, tmp_path) -> None:
    owner_id = 0
    module_key = f"pm_{uuid4().hex}"
    data_root = tmp_path / "private-module-lifecycle"
    workspace_root = data_root / "workspaces"
    install_root = data_root / "installed"
    monkeypatch.setattr(pms, "WORKSPACES_ROOT", workspace_root)
    monkeypatch.setattr(pms, "PRIVATE_MODULES_INSTALL_ROOT", install_root)
    pms.set_app_instance(app)

    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            token, owner_id = await _login(client)
            private_prefix = f"/api/private/{owner_id}/probe-private"
            _write_private_module(data_root, owner_id, module_key)
            headers = {"Authorization": f"Bearer {token}"}

            install_resp = await client.post(
                "/api/private-modules/install",
                json={"module_key": module_key},
                headers=headers,
            )
            assert install_resp.json()["success"] is True

            activate_resp = await client.post(f"/api/private-modules/{module_key}/activate", headers=headers)
            activate_data = activate_resp.json()
            assert activate_data["success"] is True
            assert activate_data["data"]["status"] == "active"
            assert activate_data["data"]["router_prefix"] == private_prefix

            unauth_resp = await client.get(f"{private_prefix}/ping")
            assert unauth_resp.status_code in {401, 403}

            route_resp = await client.get(f"{private_prefix}/ping", headers=headers)
            assert route_resp.status_code == 200
            assert route_resp.json() == {"ok": True}

            deactivate_resp = await client.post(f"/api/private-modules/{module_key}/deactivate", headers=headers)
            assert deactivate_resp.json()["success"] is True

            removed_resp = await client.get(f"{private_prefix}/ping", headers=headers)
            assert removed_resp.status_code == 404

            uninstall_resp = await client.delete(f"/api/private-modules/{module_key}", headers=headers)
            assert uninstall_resp.json()["success"] is True
    finally:
        if owner_id:
            await _cleanup_private_module(owner_id, module_key, data_root)
        else:
            shutil.rmtree(data_root, ignore_errors=True)


@pytest.mark.asyncio
async def test_private_module_activation_failure_rolls_back_runtime_route(monkeypatch, tmp_path) -> None:
    owner_id = 0
    module_key = f"pm_{uuid4().hex}"
    data_root = tmp_path / "private-module-activation-failure"
    workspace_root = data_root / "workspaces"
    install_root = data_root / "installed"
    monkeypatch.setattr(pms, "WORKSPACES_ROOT", workspace_root)
    monkeypatch.setattr(pms, "PRIVATE_MODULES_INSTALL_ROOT", install_root)
    pms.set_app_instance(app)

    original_refresh = pms._refresh_middleware_stack

    def fail_refresh(_app: object) -> None:
        raise RuntimeError("simulated middleware refresh failure")

    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            token, owner_id = await _login(client)
            private_prefix = f"/api/private/{owner_id}/probe-private"
            _write_private_module(data_root, owner_id, module_key)
            headers = {"Authorization": f"Bearer {token}"}

            install_resp = await client.post(
                "/api/private-modules/install",
                json={"module_key": module_key},
                headers=headers,
            )
            assert install_resp.json()["success"] is True

            monkeypatch.setattr(pms, "_refresh_middleware_stack", fail_refresh)
            activate_resp = await client.post(f"/api/private-modules/{module_key}/activate", headers=headers)
            activate_data = activate_resp.json()
            assert activate_resp.status_code == 500
            assert activate_data["success"] is False
            assert activate_data["data"] is None
            assert "simulated middleware refresh failure" in activate_data["error"]

            monkeypatch.setattr(pms, "_refresh_middleware_stack", original_refresh)
            original_refresh(app)
            route_resp = await client.get(f"{private_prefix}/ping", headers=headers)
            assert route_resp.status_code == 404

            uninstall_resp = await client.delete(f"/api/private-modules/{module_key}", headers=headers)
            assert uninstall_resp.json()["success"] is True
    finally:
        if owner_id:
            await _cleanup_private_module(owner_id, module_key, data_root)
        else:
            shutil.rmtree(data_root, ignore_errors=True)


@pytest.mark.asyncio
async def test_private_module_activation_failure_removes_import_registered_capability(monkeypatch, tmp_path) -> None:
    owner_id = 0
    module_key = f"pm_{uuid4().hex}"
    data_root = tmp_path / "private-module-capability-failure"
    workspace_root = data_root / "workspaces"
    install_root = data_root / "installed"
    monkeypatch.setattr(pms, "WORKSPACES_ROOT", workspace_root)
    monkeypatch.setattr(pms, "PRIVATE_MODULES_INSTALL_ROOT", install_root)
    pms.set_app_instance(app)

    original_refresh = pms._refresh_middleware_stack

    def fail_refresh(_app: object) -> None:
        raise RuntimeError("simulated middleware refresh failure")

    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            token, owner_id = await _login(client)
            private_prefix = f"/api/private/{owner_id}/probe-private"
            _write_private_module(data_root, owner_id, module_key, register_capability=True)
            headers = {"Authorization": f"Bearer {token}"}

            install_resp = await client.post(
                "/api/private-modules/install",
                json={"module_key": module_key},
                headers=headers,
            )
            assert install_resp.json()["success"] is True

            monkeypatch.setattr(pms, "_refresh_middleware_stack", fail_refresh)
            activate_resp = await client.post(f"/api/private-modules/{module_key}/activate", headers=headers)
            assert activate_resp.status_code == 500
            assert activate_resp.json()["success"] is False
            assert f"{module_key}:probe" not in _current_capability_keys()

            monkeypatch.setattr(pms, "_refresh_middleware_stack", original_refresh)
            original_refresh(app)
            route_resp = await client.get(f"{private_prefix}/ping", headers=headers)
            assert route_resp.status_code == 404
    finally:
        pms.unregister_capability(module_key, "probe")
        if owner_id:
            await _cleanup_private_module(owner_id, module_key, data_root)
        else:
            shutil.rmtree(data_root, ignore_errors=True)


@pytest.mark.asyncio
async def test_private_module_deactivate_removes_tracked_import_registered_capability(monkeypatch, tmp_path) -> None:
    owner_id = 0
    module_key = f"pm_{uuid4().hex}"
    data_root = tmp_path / "private-module-capability-deactivate"
    workspace_root = data_root / "workspaces"
    install_root = data_root / "installed"
    monkeypatch.setattr(pms, "WORKSPACES_ROOT", workspace_root)
    monkeypatch.setattr(pms, "PRIVATE_MODULES_INSTALL_ROOT", install_root)
    pms.set_app_instance(app)

    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            token, owner_id = await _login(client)
            _write_private_module(data_root, owner_id, module_key, register_capability=True)
            headers = {"Authorization": f"Bearer {token}"}

            install_resp = await client.post(
                "/api/private-modules/install",
                json={"module_key": module_key},
                headers=headers,
            )
            assert install_resp.json()["success"] is True

            activate_resp = await client.post(f"/api/private-modules/{module_key}/activate", headers=headers)
            assert activate_resp.json()["success"] is True
            assert f"{module_key}:probe" in _current_capability_keys()

            deactivate_resp = await client.post(f"/api/private-modules/{module_key}/deactivate", headers=headers)
            assert deactivate_resp.json()["success"] is True
            assert f"{module_key}:probe" not in _current_capability_keys()
    finally:
        pms.unregister_capability(module_key, "probe")
        if owner_id:
            await _cleanup_private_module(owner_id, module_key, data_root)
        else:
            shutil.rmtree(data_root, ignore_errors=True)


@pytest.mark.asyncio
async def test_private_module_import_registered_capability_is_owner_scoped(monkeypatch, tmp_path) -> None:
    owner_id = 0
    module_key = f"pm_{uuid4().hex}"
    data_root = tmp_path / "private-module-capability-scope"
    workspace_root = data_root / "workspaces"
    install_root = data_root / "installed"
    monkeypatch.setattr(pms, "WORKSPACES_ROOT", workspace_root)
    monkeypatch.setattr(pms, "PRIVATE_MODULES_INSTALL_ROOT", install_root)
    pms.set_app_instance(app)

    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            token, owner_id = await _login(client)
            _write_private_module(data_root, owner_id, module_key, register_capability=True)
            headers = {"Authorization": f"Bearer {token}"}

            install_resp = await client.post(
                "/api/private-modules/install",
                json={"module_key": module_key},
                headers=headers,
            )
            assert install_resp.json()["success"] is True

            activate_resp = await client.post(f"/api/private-modules/{module_key}/activate", headers=headers)
            assert activate_resp.json()["success"] is True

            snapshot = _current_capability_snapshot()
            assert snapshot[f"{module_key}:probe"]["owner_id"] == owner_id

            owner_caps = list_capabilities(role="admin", caller=f"user:{owner_id}")
            other_caps = list_capabilities(role="admin", caller=f"user:{owner_id + 9999}")
            assert any(item["module"] == module_key and item["action"] == "probe" for item in owner_caps)
            assert not any(item["module"] == module_key and item["action"] == "probe" for item in other_caps)

            owner_result = await call_capability(
                module_key,
                "probe",
                {},
                caller=f"user:{owner_id}",
                caller_role="admin",
            )
            assert owner_result["data"]["caller"] == f"user:{owner_id}"
            with pytest.raises(PermissionDenied):
                await call_capability(
                    module_key,
                    "probe",
                    {},
                    caller=f"user:{owner_id + 9999}",
                    caller_role="admin",
                )

            capabilities_resp = await client.get("/api/modules/capabilities", headers=headers)
            assert capabilities_resp.json()["success"] is True
            assert any(
                item["module"] == module_key and item["action"] == "probe"
                for item in capabilities_resp.json()["data"]
            )
    finally:
        pms.unregister_capability(module_key, "probe")
        if owner_id:
            await _cleanup_private_module(owner_id, module_key, data_root)
        else:
            shutil.rmtree(data_root, ignore_errors=True)


@pytest.mark.asyncio
async def test_private_module_activation_failure_cannot_override_public_capability(monkeypatch, tmp_path) -> None:
    owner_id = 0
    module_key = f"pm_{uuid4().hex}"
    data_root = tmp_path / "private-module-capability-override"
    workspace_root = data_root / "workspaces"
    install_root = data_root / "installed"
    monkeypatch.setattr(pms, "WORKSPACES_ROOT", workspace_root)
    monkeypatch.setattr(pms, "PRIVATE_MODULES_INSTALL_ROOT", install_root)
    pms.set_app_instance(app)

    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            token, owner_id = await _login(client)
            _write_private_module(
                data_root,
                owner_id,
                module_key,
                register_capability=True,
                capability_module_key="_self",
                capability_action="echo",
            )
            headers = {"Authorization": f"Bearer {token}"}

            install_resp = await client.post(
                "/api/private-modules/install",
                json={"module_key": module_key},
                headers=headers,
            )
            assert install_resp.json()["success"] is True

            activate_resp = await client.post(f"/api/private-modules/{module_key}/activate", headers=headers)
            activate_data = activate_resp.json()
            assert activate_resp.status_code == 500
            assert activate_data["success"] is False
            assert "cannot override existing capability" in activate_data["error"]

            echo_result = await call_capability(
                "_self",
                "echo",
                {"sentinel": True},
                caller=f"user:{owner_id}",
                caller_role="admin",
            )
            assert echo_result == {"echo": {"sentinel": True}, "caller": f"user:{owner_id}"}
    finally:
        if owner_id:
            await _cleanup_private_module(owner_id, module_key, data_root)
        else:
            shutil.rmtree(data_root, ignore_errors=True)


@pytest.mark.asyncio
async def test_private_module_rollback_failure_exposes_success_false(monkeypatch, tmp_path) -> None:
    owner_id = 0
    module_key = f"pm_{uuid4().hex}"
    data_root = tmp_path / "private-module-rollback-failure"
    workspace_root = data_root / "workspaces"
    install_root = data_root / "installed"
    monkeypatch.setattr(pms, "WORKSPACES_ROOT", workspace_root)
    monkeypatch.setattr(pms, "PRIVATE_MODULES_INSTALL_ROOT", install_root)
    pms.set_app_instance(app)

    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            token, owner_id = await _login(client)
            private_prefix = f"/api/private/{owner_id}/probe-private"
            _write_private_module(data_root, owner_id, module_key)
            headers = {"Authorization": f"Bearer {token}"}

            install_resp = await client.post(
                "/api/private-modules/install",
                json={"module_key": module_key},
                headers=headers,
            )
            assert install_resp.json()["success"] is True

            activate_resp = await client.post(f"/api/private-modules/{module_key}/activate", headers=headers)
            assert activate_resp.json()["success"] is True
            assert activate_resp.json()["data"]["status"] == "active"

            router_path = install_root / str(owner_id) / module_key / "backend" / "router.py"
            router_path.write_text("this is not valid python\n")

            rollback_resp = await client.post(f"/api/private-modules/{module_key}/rollback", headers=headers)
            rollback_data = rollback_resp.json()
            assert rollback_resp.status_code == 500
            assert rollback_data["success"] is False
            assert rollback_data["data"] is None
            assert rollback_data["error"] is not None

            route_resp = await client.get(f"{private_prefix}/ping", headers=headers)
            assert route_resp.status_code == 404

            deactivate_resp = await client.post(f"/api/private-modules/{module_key}/deactivate", headers=headers)
            assert deactivate_resp.json()["success"] is True

            uninstall_resp = await client.delete(f"/api/private-modules/{module_key}", headers=headers)
            assert uninstall_resp.json()["success"] is True
    finally:
        if owner_id:
            await _cleanup_private_module(owner_id, module_key, data_root)
        else:
            shutil.rmtree(data_root, ignore_errors=True)
