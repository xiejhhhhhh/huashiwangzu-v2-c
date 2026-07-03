"""FastAPI router for browser-tools module.

Exposes 9 cross-module capabilities for isolated browser operations:
  browser-tools:open         — Open URL in isolated browser context
  browser-tools:read_text    — Extract visible text from current page
  browser-tools:list_links   — List visible links on current page
  browser-tools:click        — Click an element by selector/text
  browser-tools:type         — Type text into an input field
  browser-tools:wait_for     — Wait for element/navigation/time
  browser-tools:screenshot   — Take screenshot, save to workspace
  browser-tools:download     — Download file to workspace
  browser-tools:close        — Close browser session

Security:
  - Uses isolated Playwright browser context (temp user data dir)
  - Cookie/localStorage never returned to caller
  - Downloads go to workspace only
  - URL filtering blocks localhost, file://, private subnets
  - Timeout, page count, download size limits enforced
  - Camera, mic, clipboard, geo disabled by default
"""

from __future__ import annotations

import importlib.util
import logging
from pathlib import Path

from app.core.exceptions import ValidationError
from app.middleware.auth import require_permission
from app.models.user import User
from app.schemas.common import ApiResponse
from fastapi import APIRouter, Depends
from pydantic import BaseModel

logger = logging.getLogger("v2.browser-tools")

router = APIRouter(prefix="/api/browser-tools", tags=["browser-tools"])

_DEFAULT_TIMEOUT = 30
_MAX_PAGE_SIZE = 10 * 1024 * 1024  # 10 MB


# ── HTTP request schemas ──

class OpenRequest(BaseModel):
    url: str
    session_id: str | None = None
    width: int = 1280
    height: int = 720
    timeout: int = _DEFAULT_TIMEOUT


class ReadTextRequest(BaseModel):
    session_id: str | None = None


class ListLinksRequest(BaseModel):
    session_id: str | None = None


class ClickRequest(BaseModel):
    session_id: str | None = None
    selector: str = ""
    text: str = ""
    timeout: int = _DEFAULT_TIMEOUT


class TypeRequest(BaseModel):
    session_id: str | None = None
    selector: str = ""
    text: str = ""
    timeout: int = _DEFAULT_TIMEOUT


class WaitForRequest(BaseModel):
    session_id: str | None = None
    selector: str = ""
    timeout: int = _DEFAULT_TIMEOUT
    wait_for_navigation: bool = False


class ScreenshotRequest(BaseModel):
    session_id: str | None = None
    full_page: bool = False


class DownloadRequest(BaseModel):
    session_id: str | None = None
    url: str = ""
    timeout: int = _DEFAULT_TIMEOUT


class CloseRequest(BaseModel):
    session_id: str | None = None


# ── HTTP endpoints ──

def _browser_response(result: dict):
    if isinstance(result, dict) and result.get("error"):
        raise ValidationError(str(result["error"]))
    if isinstance(result, dict) and "success" in result and "data" in result:
        return ApiResponse(data=result.get("data"))
    return ApiResponse(data=result)


@router.get("/health")
async def health():
    return ApiResponse(data={"module": "browser-tools", "status": "ok"})


@router.post("/open")
async def http_open(
    body: OpenRequest,
    user: User = Depends(require_permission("viewer")),
):
    from .handlers.browser import _open
    result = await _open(body.model_dump(), f"user:{user.id}")
    return _browser_response(result)


@router.post("/read-text")
async def http_read_text(
    body: ReadTextRequest,
    user: User = Depends(require_permission("viewer")),
):
    from .handlers.browser import _read_text
    result = await _read_text(body.model_dump(), f"user:{user.id}")
    return _browser_response(result)


@router.post("/list-links")
async def http_list_links(
    body: ListLinksRequest,
    user: User = Depends(require_permission("viewer")),
):
    from .handlers.browser import _list_links
    result = await _list_links(body.model_dump(), f"user:{user.id}")
    return _browser_response(result)


@router.post("/click")
async def http_click(
    body: ClickRequest,
    user: User = Depends(require_permission("viewer")),
):
    from .handlers.browser import _click
    result = await _click(body.model_dump(), f"user:{user.id}")
    return _browser_response(result)


@router.post("/type")
async def http_type(
    body: TypeRequest,
    user: User = Depends(require_permission("viewer")),
):
    from .handlers.browser import _type
    result = await _type(body.model_dump(), f"user:{user.id}")
    return _browser_response(result)


@router.post("/wait-for")
async def http_wait_for(
    body: WaitForRequest,
    user: User = Depends(require_permission("viewer")),
):
    from .handlers.browser import _wait_for
    result = await _wait_for(body.model_dump(), f"user:{user.id}")
    return _browser_response(result)


@router.post("/screenshot")
async def http_screenshot(
    body: ScreenshotRequest,
    user: User = Depends(require_permission("viewer")),
):
    from .handlers.browser import _screenshot
    result = await _screenshot(body.model_dump(), f"user:{user.id}")
    return _browser_response(result)


@router.post("/download")
async def http_download(
    body: DownloadRequest,
    user: User = Depends(require_permission("viewer")),
):
    from .handlers.browser import _download
    result = await _download(body.model_dump(), f"user:{user.id}")
    return _browser_response(result)


@router.post("/close")
async def http_close(
    body: CloseRequest,
    user: User = Depends(require_permission("viewer")),
):
    from .handlers.browser import _close
    result = await _close(body.model_dump(), f"user:{user.id}")
    return _browser_response(result)


def _register_browser_capabilities() -> None:
    try:
        from .handlers import browser  # noqa: F401
        return
    except ModuleNotFoundError:
        handler_path = Path(__file__).resolve().parent / "handlers" / "browser.py"
        spec = importlib.util.spec_from_file_location("browser_tools_dynamic_handlers", handler_path)
        if not spec or not spec.loader:
            raise
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)


_register_browser_capabilities()
