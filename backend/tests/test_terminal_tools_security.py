"""Tests for terminal-tools security integration.

Imports module code via the huashiwangzu_modules namespace (same mechanism
the framework uses at runtime) so relative imports within handlers work.
"""

import importlib
import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[2]
MODULES_DIR = PROJECT_ROOT / "modules"


def _init_namespace():
    """Set up the huashiwangzu_modules namespace like the framework does."""
    if "huashiwangzu_modules" not in sys.modules:
        import types
        top_pkg = types.ModuleType("huashiwangzu_modules")
        top_pkg.__path__ = []
        sys.modules["huashiwangzu_modules"] = top_pkg

    safe_key = "terminal_tools"
    pkg_name = f"huashiwangzu_modules.{safe_key}"
    if pkg_name not in sys.modules:
        backend_dir = MODULES_DIR / "terminal-tools" / "backend"
        import types
        pkg = types.ModuleType(pkg_name)
        pkg.__path__ = [str(backend_dir)]
        sys.modules[pkg_name] = pkg

    sys.modules.pop("backend", None)


def _load_module(module_key: str, module_path: str):
    """Load a module under the huashiwangzu_modules namespace."""
    _init_namespace()
    safe_key = module_key.replace("-", "_")
    fq_name = f"huashiwangzu_modules.{safe_key}.{module_path.replace('/', '.')}"
    return importlib.import_module(fq_name)


# Load handlers using namespace
exec_mod = _load_module("terminal-tools", "handlers.exec")
file_ops_mod = _load_module("terminal-tools", "handlers.file_ops")
router_mod = _load_module("terminal-tools", "router")


# ── exec handler security ──────────────────────────────────────────────

@pytest.mark.asyncio
async def test_exec_blocks_dangerous_command():
    result = await exec_mod._exec({"command": "sudo ls"}, "user:1")
    assert result.get("success") is False
    err = result.get("error", "").lower()
    assert "dangerous" in err or "blocked" in err


@pytest.mark.asyncio
async def test_exec_blocks_path_escape():
    result = await exec_mod._exec({"command": "cat ../secret"}, "user:1")
    assert result.get("success") is False
    err = result.get("error", "").lower()
    assert "outside" in err or "blocked" in err or "escape" in err


# ── file_ops handler security ──────────────────────────────────────────

@pytest.mark.asyncio
async def test_write_file_rejects_dotdot():
    result = await file_ops_mod._write_file({"path": "../x", "content": "test"}, "user:1")
    assert result.get("success") is False
    err = result.get("error", "").lower()
    assert "workspace" in err or "boundary" in err


@pytest.mark.asyncio
async def test_read_file_rejects_dotdot():
    result = await file_ops_mod._read_file({"path": "../x"}, "user:1")
    assert result.get("success") is False
    err = result.get("error", "").lower()
    assert "workspace" in err or "boundary" in err


@pytest.mark.asyncio
async def test_list_workspace_rejects_absolute():
    result = await file_ops_mod._list_workspace({"path": "/etc"}, "user:1")
    assert result.get("success") is False
    err = result.get("error", "").lower()
    assert "workspace" in err or "boundary" in err


def test_http_response_preserves_inner_failure_status():
    response = router_mod._terminal_response({
        "success": False,
        "error": "Dangerous command blocked: sudo command",
        "command": "sudo whoami",
    })

    assert response.success is False
    assert response.error == "Dangerous command blocked: sudo command"
    assert response.data["success"] is False
