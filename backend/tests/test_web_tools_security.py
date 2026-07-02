"""Tests for web-tools SSRF protection integration.

Imports module code via the same namespace mechanism the framework uses.
"""

import importlib
import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[2]
MODULES_DIR = PROJECT_ROOT / "modules"


def _init_namespace():
    if "huashiwangzu_modules" not in sys.modules:
        import types
        top_pkg = types.ModuleType("huashiwangzu_modules")
        top_pkg.__path__ = []
        sys.modules["huashiwangzu_modules"] = top_pkg

    safe_key = "web_tools"
    pkg_name = f"huashiwangzu_modules.{safe_key}"
    if pkg_name not in sys.modules:
        backend_dir = MODULES_DIR / "web-tools" / "backend"
        import types
        pkg = types.ModuleType(pkg_name)
        pkg.__path__ = [str(backend_dir)]
        sys.modules[pkg_name] = pkg

    sys.modules.pop("backend", None)


def _load_router(module_key: str):
    _init_namespace()
    safe_key = module_key.replace("-", "_")
    fq_name = f"huashiwangzu_modules.{safe_key}.router"
    return importlib.import_module(fq_name)


router_mod = _load_router("web-tools")


@pytest.mark.asyncio
async def test_fetch_rejects_localhost():
    result = await router_mod._cap_fetch({"url": "http://127.0.0.1:33000"}, "user:1")
    assert result["success"] is False
    assert not result.get("title") and not result.get("text")
    assert "error" in result
    assert result["error"]


@pytest.mark.asyncio
async def test_fetch_rejects_metadata():
    result = await router_mod._cap_fetch({"url": "http://169.254.169.254/latest/meta-data"}, "user:1")
    assert result["success"] is False
    assert result["error"]


@pytest.mark.asyncio
async def test_fetch_rejects_private():
    result = await router_mod._cap_fetch({"url": "http://10.0.0.1/admin"}, "user:1")
    assert result["success"] is False
    assert result["error"]


@pytest.mark.asyncio
async def test_fetch_rejects_file_scheme():
    result = await router_mod._cap_fetch({"url": "file:///etc/passwd"}, "user:1")
    assert result["success"] is False
    assert result["error"]


@pytest.mark.asyncio
async def test_fetch_rejects_userinfo():
    result = await router_mod._cap_fetch({"url": "https://user:pass@example.com"}, "user:1")
    assert result["success"] is False
    assert result["error"]


# The SSRF rejection tests above validate the security integration.
# Full happy-path with httpx mocking is tested via the core url_safety tests.
# This test verifies the SSRF check does not falsely reject public HTTPS URLs.
@pytest.mark.asyncio
async def test_fetch_public_url_passes_ssrf_check():
    """A valid public HTTPS URL should pass the SSRF check (non-blocked error may
    occur from network operations, but must NOT be an SSRF error)."""
    result = await router_mod._cap_fetch({"url": "https://example.com", "max_chars": 500}, "user:1")
    err = (result.get("error") or "").lower()
    assert "internal" not in err
    assert "ssrf" not in err
    assert "private" not in err or "blocked" not in err


def test_http_response_preserves_fetch_failure_status():
    response = router_mod._web_response({
        "success": False,
        "url": "http://127.0.0.1:33000",
        "title": "",
        "text": "",
        "truncated": False,
        "error": "URL targets a private/internal address",
    })

    assert response.success is False
    assert response.error == "URL targets a private/internal address"
    assert response.data["success"] is False
