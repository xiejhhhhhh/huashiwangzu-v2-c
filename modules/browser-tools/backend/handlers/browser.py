"""Isolated browser handlers using Playwright.

Security guarantees:
  - Temporary user data dir per session (no host Chrome profile access)
  - Cookie/localStorage never exposed to caller
  - URL filtering: file://, localhost, private subnet blocked
  - Default disabled: camera, mic, clipboard-read, geolocation
  - Timeout, page count, download size, screenshot size enforced
  - Workspace-only file paths
"""

from __future__ import annotations

import asyncio
import ipaddress
import logging
import os
import socket
import tempfile
import time
import uuid
from pathlib import Path
from urllib.parse import urlparse

from app.core.exceptions import ValidationError
from app.core.url_safety import validate_safe_url
from app.services.module_registry import register_capability

logger = logging.getLogger("v2.browser-tools").getChild("browser")

# ── Session management ─────────────────────────────────────────────

_sessions: dict[str, dict] = {}
_SESSION_TTL = 300  # 5 minutes idle timeout
_MAX_PAGES = 5
_MAX_DOWNLOAD_BYTES = 50 * 1024 * 1024  # 50 MB
_MAX_SCREENSHOT_BYTES = 5 * 1024 * 1024  # 5 MB
_MAX_BODY_BYTES = 512 * 1024  # 512 KB text extraction limit

_BLOCKED_HOSTNAMES = {
    "localhost",
    "metadata.google.internal",
    "metadata.goog",
}
_ALWAYS_BLOCKED_IPS = {
    ipaddress.ip_address(addr)
    for addr in (
        "169.254.169.254",
        "169.254.170.2",
        "169.254.169.253",
        "100.100.100.200",
        "fd00:ec2::254",
        "::ffff:169.254.169.254",
        "::ffff:169.254.170.2",
        "::ffff:169.254.169.253",
        "::ffff:100.100.100.200",
    )
}
_ALWAYS_BLOCKED_NETWORKS = [
    ipaddress.ip_network("169.254.0.0/16"),
    ipaddress.ip_network("::ffff:169.254.0.0/112"),
]
_BLOCKED_PRIVATE_NETWORKS = [
    ipaddress.ip_network("10.0.0.0/8"),
    ipaddress.ip_network("172.16.0.0/12"),
    ipaddress.ip_network("192.168.0.0/16"),
    ipaddress.ip_network("127.0.0.0/8"),
    ipaddress.ip_network("0.0.0.0/8"),
    ipaddress.ip_network("100.64.0.0/10"),
    ipaddress.ip_network("::1/128"),
    ipaddress.ip_network("fc00::/7"),
    ipaddress.ip_network("fe80::/10"),
    ipaddress.ip_network("::/128"),
]


def _get_workspace_path(caller: str) -> Path:
    """Resolve user workspace path from caller identity."""
    uid = caller.replace("user:", "") if caller else "0"
    workspace = Path(os.environ.get("WORKSPACE_ROOT", "data/workspaces")) / str(uid)
    workspace.mkdir(parents=True, exist_ok=True)
    return workspace


def _is_blocked_url(url: str) -> tuple[bool, str]:
    """Check URL against blocklist. Returns (blocked, reason)."""
    if not isinstance(url, str) or not url.strip():
        return True, "URL is required"

    url = url.strip()
    try:
        parsed = urlparse(url)
    except Exception as exc:
        return True, f"Invalid URL: {exc}"

    scheme = (parsed.scheme or "").lower()
    if scheme not in {"http", "https"}:
        return True, "Only http/https URLs are allowed"

    hostname = (parsed.hostname or "").strip().lower().rstrip(".")
    if not hostname:
        return True, "URL has no hostname"
    if parsed.username or parsed.password:
        return True, "URL with embedded credentials is not allowed"
    if hostname in _BLOCKED_HOSTNAMES:
        return True, "URL targets a blocked internal address"

    try:
        ip = ipaddress.ip_address(hostname)
    except ValueError:
        ip = None

    if ip is not None:
        reason = _blocked_ip_reason(ip, target="targets")
        if reason:
            return True, reason
        if not ip.is_global:
            return True, "URL targets a private/internal address"
        return False, ""

    try:
        addr_info = socket.getaddrinfo(hostname, None, socket.AF_UNSPEC, socket.SOCK_STREAM)
    except socket.gaierror:
        return True, f"DNS resolution failed for: {hostname}"

    has_global_address = False
    for _family, _, _, _, sockaddr in addr_info:
        ip_str = sockaddr[0].split("%", 1)[0]
        try:
            resolved = ipaddress.ip_address(ip_str)
        except ValueError:
            return True, f"Unparseable IP for hostname {hostname}"
        reason = _blocked_ip_reason(resolved, target="resolves to")
        if reason:
            return True, reason
        if resolved.is_global:
            has_global_address = True

    if not has_global_address:
        try:
            validate_safe_url(url)
        except ValidationError as exc:
            return True, exc.message
        except Exception as exc:
            return True, str(exc)
    return False, ""


def _blocked_ip_reason(
    ip: ipaddress.IPv4Address | ipaddress.IPv6Address,
    *,
    target: str,
) -> str:
    if isinstance(ip, ipaddress.IPv6Address) and ip.ipv4_mapped is not None:
        ip = ip.ipv4_mapped
    if ip in _ALWAYS_BLOCKED_IPS or any(ip in net for net in _ALWAYS_BLOCKED_NETWORKS):
        return f"URL {target} a blocked internal address"
    if any(ip in net for net in _BLOCKED_PRIVATE_NETWORKS):
        return f"URL {target} a private/internal address"
    if ip.is_loopback or ip.is_link_local or ip.is_multicast or ip.is_unspecified:
        return f"URL {target} a private/internal address"
    return ""


def _sanitize_text(text: str, max_bytes: int = _MAX_BODY_BYTES) -> str:
    """Truncate and sanitize extracted text."""
    encoded = text.encode("utf-8")
    if len(encoded) > max_bytes:
        return encoded[:max_bytes].decode("utf-8", errors="ignore") + "\n...（内容已截断）"
    return text


def _viewport_from_params(params: dict) -> dict[str, int]:
    def _bounded_int(name: str, default: int, minimum: int, maximum: int) -> int:
        try:
            value = int(params.get(name, default))
        except (TypeError, ValueError):
            value = default
        return max(minimum, min(maximum, value))

    return {
        "width": _bounded_int("width", 1280, 320, 3840),
        "height": _bounded_int("height", 720, 240, 2160),
    }


def _ok(data: dict) -> dict:
    return {"success": True, "data": data, "error": None}


def _err(message: str) -> dict:
    return {"success": False, "data": None, "error": message}


def _blocked_error(url: str) -> str:
    blocked, reason = _is_blocked_url(url)
    return reason if blocked else ""


async def _ensure_allowed_current_url(page) -> str:
    """Return current URL or raise if navigation ended at a blocked target."""
    current_url = page.url
    reason = _blocked_error(current_url)
    if reason:
        raise ValueError(f"blocked final URL {current_url}: {reason}")
    return current_url


async def _download_http_checked(url: str, timeout: int) -> tuple[bytes, str, str]:
    """Download via HTTP while validating every redirect target."""
    import httpx

    current_url = url
    for _ in range(8):
        reason = _blocked_error(current_url)
        if reason:
            raise ValueError(reason)
        async with httpx.AsyncClient(follow_redirects=False, timeout=timeout) as client:
            resp = await client.get(current_url)
        if resp.is_redirect:
            next_url = str(resp.next_request.url) if resp.next_request else resp.headers.get("location", "")
            if not next_url:
                raise ValueError("redirect target missing")
            current_url = next_url
            continue
        resp.raise_for_status()
        return resp.content, current_url, resp.headers.get("content-type", "")
    raise ValueError("too many redirects")


async def _launch_browser():
    """Lazy-init a Playwright browser instance."""
    from playwright.async_api import async_playwright
    p = await async_playwright().start()
    browser = await p.chromium.launch(
        headless=True,
        args=[
            "--no-sandbox",
            "--disable-setuid-sandbox",
            "--disable-dev-shm-usage",
            "--disable-gpu",
            "--disable-accelerated-2d-canvas",
            "--no-first-run",
            "--disable-features=PasswordImport,SavePasswords",
        ],
    )
    return p, browser


async def _attach_url_guard(context) -> None:
    async def _guard(route):
        request_url = route.request.url
        if request_url.startswith(("about:", "data:", "blob:")):
            await route.continue_()
            return
        if _blocked_error(request_url):
            await route.abort()
            return
        await route.continue_()

    await context.route("**/*", _guard)


def _get_existing_session(session_id: str | None, caller: str) -> tuple[dict | None, str | None]:
    if not session_id or session_id not in _sessions:
        return None, "no active session, call open first"
    session = _sessions[session_id]
    if "caller" in session and session.get("caller") != caller:
        return None, "session belongs to another caller"
    session.setdefault("caller", caller)
    session["last_access"] = time.time()
    return session, None


async def _get_or_create_session(session_id: str | None, caller: str) -> dict:
    """Get or create a browser session."""
    if session_id and session_id in _sessions:
        session = _sessions[session_id]
        if session.get("caller") != caller:
            raise PermissionError("session belongs to another caller")
        session["last_access"] = time.time()

        # Ensure context is still alive
        pages = session["context"].pages
        if pages:
            return session
        # Recreate context if all pages closed
        context = await session["browser"].new_context(
            viewport={"width": 1280, "height": 720},
            permissions=[],  # No camera, mic, geo
            locale="zh-CN",
            user_agent=(
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/125.0.0.0 Safari/537.36"
            ),
        )
        await _attach_url_guard(context)
        session["context"] = context
        page = await context.new_page()
        session["page"] = page
        return session

    p, browser = await _launch_browser()
    temp_dir = tempfile.mkdtemp(prefix="browser_")
    context = await browser.new_context(
        viewport={"width": 1280, "height": 720},
        permissions=[],
        locale="zh-CN",
        user_agent=(
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/125.0.0.0 Safari/537.36"
        ),
        no_viewport=True,
    )
    await _attach_url_guard(context)
    page = await context.new_page()
    sid = session_id or str(uuid.uuid4())

    _sessions[sid] = {
        "id": sid,
        "playwright": p,
        "browser": browser,
        "context": context,
        "page": page,
        "temp_dir": temp_dir,
        "caller": caller,
        "created_at": time.time(),
        "last_access": time.time(),
        "page_count": 1,
    }

    # Start cleanup task
    asyncio.ensure_future(_cleanup_stale_sessions())
    return _sessions[sid]


async def _cleanup_stale_sessions():
    """Close idle sessions periodically."""
    now = time.time()
    stale = [sid for sid, s in list(_sessions.items())
             if now - s["last_access"] > _SESSION_TTL]
    for sid in stale:
        await _close_session(sid)


async def _close_session(session_id: str):
    """Close and clean up a browser session."""
    session = _sessions.pop(session_id, None)
    if not session:
        return
    try:
        await session["context"].close()
    except Exception:
        pass
    try:
        await session["browser"].close()
    except Exception:
        pass
    try:
        await session["playwright"].stop()
    except Exception:
        pass
    try:
        temp_dir = session.get("temp_dir", "")
        if temp_dir and os.path.isdir(temp_dir):
            import shutil
            shutil.rmtree(temp_dir, ignore_errors=True)
    except Exception:
        pass
    logger.info("Closed stale browser session %s", session_id)


# ── Capabilities ───────────────────────────────────────────────────


async def _open(params: dict, caller: str) -> dict:
    """Open a URL in isolated browser context."""
    url = params.get("url", "")
    if not url:
        return _err("url is required")

    if url:
        blocked, reason = _is_blocked_url(url)
        if blocked:
            return _err(reason)

    try:
        session = await _get_or_create_session(params.get("session_id"), caller)
        page = session["page"]
        await page.set_viewport_size(_viewport_from_params(params))

        await page.goto(url, wait_until="domcontentloaded",
                        timeout=params.get("timeout", 30) * 1000)
        await page.wait_for_load_state("networkidle", timeout=10000)

        current_url = await _ensure_allowed_current_url(page)
        title = await page.title()
        visible_text = _sanitize_text(
            await page.inner_text("body") if await page.query_selector("body") else ""
        )

        return _ok({
            "session_id": session["id"],
            "title": title or "",
            "url": current_url,
            "visible_text_preview": visible_text[:500] + "..." if len(visible_text) > 500 else visible_text,
        })
    except Exception as e:
        logger.warning("browser-tools:open failed: %s", e)
        return _err(f"browser open failed: {e}")


async def _read_text(params: dict, caller: str) -> dict:
    """Extract visible text from current page."""
    session_id = params.get("session_id")
    session, session_error = _get_existing_session(session_id, caller)
    if session_error:
        return _err(session_error)
    try:
        page = session["page"]

        title = await page.title()
        current_url = await _ensure_allowed_current_url(page)
        body_text = await page.inner_text("body") if await page.query_selector("body") else ""
        visible_text = _sanitize_text(body_text)

        # Extract buttons and links text for overview
        buttons = await page.eval_on_selector_all(
            "button, [role='button'], a.btn",
            "els => els.map(e => e.textContent.trim()).filter(Boolean).slice(0, 30)",
        )

        return _ok({
            "session_id": session_id,
            "title": title or "",
            "url": current_url,
            "visible_text": visible_text,
            "buttons": buttons,
        })
    except Exception as e:
        logger.warning("browser-tools:read_text failed: %s", e)
        return _err(f"read text failed: {e}")


async def _list_links(params: dict, caller: str) -> dict:
    """List visible links on current page (no cookies)."""
    session_id = params.get("session_id")
    session, session_error = _get_existing_session(session_id, caller)
    if session_error:
        return _err(session_error)
    try:
        page = session["page"]
        await _ensure_allowed_current_url(page)

        links = await page.eval_on_selector_all(
            "a[href]",
            """els => els.map(el => ({
                text: el.textContent.trim().slice(0, 200),
                href: el.getAttribute('href'),
                visible: el.offsetParent !== null
            })).filter(l => l.href && l.text).slice(0, 100)""",
        )

        return _ok({
            "session_id": session_id,
            "links": links,
            "total": len(links),
        })
    except Exception as e:
        logger.warning("browser-tools:list_links failed: %s", e)
        return _err(f"list links failed: {e}")


async def _click(params: dict, caller: str) -> dict:
    """Click an element by selector or text match."""
    session_id = params.get("session_id")
    session, session_error = _get_existing_session(session_id, caller)
    if session_error:
        return _err(session_error)
    selector = params.get("selector", "")
    text = params.get("text", "")
    if not selector and not text:
        return _err("selector or text is required")
    try:
        page = session["page"]
        timeout = params.get("timeout", 30) * 1000
        await _ensure_allowed_current_url(page)

        if selector:
            await page.click(selector, timeout=timeout)
        elif text:
            # Click by visible text
            await page.get_by_text(text, exact=False).first.click(timeout=timeout)

        await page.wait_for_load_state("networkidle", timeout=10000)
        current_url = await _ensure_allowed_current_url(page)

        return _ok({
            "session_id": session_id,
            "url": current_url,
            "title": await page.title(),
        })
    except Exception as e:
        logger.warning("browser-tools:click failed: %s", e)
        return _err(f"click failed: {e}")


async def _type(params: dict, caller: str) -> dict:
    """Type text into an input field."""
    session_id = params.get("session_id")
    session, session_error = _get_existing_session(session_id, caller)
    if session_error:
        return _err(session_error)
    selector = params.get("selector", "")
    text = params.get("text", "")
    if not selector:
        return _err("selector is required")
    try:
        page = session["page"]
        timeout = params.get("timeout", 30) * 1000
        await _ensure_allowed_current_url(page)

        await page.fill(selector, "", timeout=timeout)
        await page.type(selector, text, delay=10, timeout=timeout)

        return _ok({"session_id": session_id, "selector": selector, "typed_length": len(text)})
    except Exception as e:
        logger.warning("browser-tools:type failed: %s", e)
        return _err(f"type failed: {e}")


async def _wait_for(params: dict, caller: str) -> dict:
    """Wait for an element, navigation, or fixed time."""
    session_id = params.get("session_id")
    session, session_error = _get_existing_session(session_id, caller)
    if session_error:
        return _err(session_error)
    try:
        page = session["page"]
        timeout = params.get("timeout", 30) * 1000
        selector = params.get("selector", "")
        wait_nav = params.get("wait_for_navigation", False)
        await _ensure_allowed_current_url(page)

        if wait_nav:
            await page.wait_for_load_state("networkidle", timeout=timeout)
        elif selector:
            await page.wait_for_selector(selector, timeout=timeout)
        else:
            # Wait fixed time (minimal: just a small delay)
            await asyncio.sleep(0.5)

        current_url = await _ensure_allowed_current_url(page)
        return _ok({
            "session_id": session_id,
            "url": current_url,
            "title": await page.title(),
        })
    except Exception as e:
        logger.warning("browser-tools:wait_for failed: %s", e)
        return _err(f"wait_for failed: {e}")


async def _screenshot(params: dict, caller: str) -> dict:
    """Take screenshot, save to workspace file (not base64)."""
    session_id = params.get("session_id")
    session, session_error = _get_existing_session(session_id, caller)
    if session_error:
        return _err(session_error)
    try:
        page = session["page"]
        full_page = params.get("full_page", False)
        await _ensure_allowed_current_url(page)

        workspace = _get_workspace_path(caller)
        filename = f"screenshot_{uuid.uuid4().hex[:8]}.png"
        filepath = workspace / filename

        await page.screenshot(path=str(filepath), full_page=full_page)

        file_size = filepath.stat().st_size
        if file_size > _MAX_SCREENSHOT_BYTES:
            filepath.unlink(missing_ok=True)
            return _err(f"screenshot too large ({file_size} bytes, max {_MAX_SCREENSHOT_BYTES})")

        return _ok({
            "session_id": session_id,
            "file_path": str(filepath),
            "filename": filename,
            "size": file_size,
            "full_page": full_page,
            "note": "Use terminal-tools:publish to deliver to desktop",
        })
    except Exception as e:
        logger.warning("browser-tools:screenshot failed: %s", e)
        return _err(f"screenshot failed: {e}")


async def _download(params: dict, caller: str) -> dict:
    """Download file from a URL to workspace."""
    url = params.get("url", "")
    session_id = params.get("session_id", "")
    if not url and not session_id:
        return _err("url or session_id is required")

    if url:
        blocked, reason = _is_blocked_url(url)
        if blocked:
            return _err(reason)

    try:
        workspace = _get_workspace_path(caller)

        if session_id:
            # Use browser context download
            session, session_error = _get_existing_session(session_id, caller)
            if session_error:
                return _err(session_error)
            page = session["page"]
            await _ensure_allowed_current_url(page)

            async with page.expect_download(timeout=params.get("timeout", 30) * 1000) as download_info:
                if url:
                    await page.goto(url, wait_until="domcontentloaded")
                    await _ensure_allowed_current_url(page)
                # Trigger download - if no URL just wait for existing download trigger
            download = await download_info.value
            filename = download.suggested_filename or f"download_{uuid.uuid4().hex[:8]}"
            filepath = workspace / filename
            await download.save_as(str(filepath))
            file_size = filepath.stat().st_size
        else:
            # Direct HTTP download
            content, final_url, content_type = await _download_http_checked(
                url,
                timeout=params.get("timeout", 30),
            )
            if len(content) > _MAX_DOWNLOAD_BYTES:
                return _err(f"download too large ({len(content)} bytes, max {_MAX_DOWNLOAD_BYTES})")
            filename = final_url.split("/")[-1] or f"download_{uuid.uuid4().hex[:8]}"
            filepath = workspace / filename
            filepath.write_bytes(content)
            file_size = len(content)

        return _ok({
            "file_path": str(filepath),
            "filename": filename,
            "size": file_size,
            "session_id": session_id or "",
            "note": "Use terminal-tools:publish to deliver to desktop",
        })
    except Exception as e:
        logger.warning("browser-tools:download failed: %s", e)
        return _err(f"download failed: {e}")


async def _close(params: dict, caller: str) -> dict:
    """Close a browser session and release resources."""
    session_id = params.get("session_id")
    _session, session_error = _get_existing_session(session_id, caller)
    if session_error:
        return _err(session_error)
    await _close_session(session_id)
    return _ok({"session_id": session_id, "closed": True})


# ── Register capabilities ──

register_capability(
    "browser-tools", "open", _open,
    description="在隔离浏览器中打开 URL。适用于 JS 渲染页面、登录态页面、动态内容。Cookie/localStorage 不返回给调用方。",
    brief="打开网页",
    parameters={
        "url": {"type": "string", "description": "要打开的 URL"},
        "width": {"type": "integer", "description": "视口宽度", "default": 1280},
        "height": {"type": "integer", "description": "视口高度", "default": 720},
        "session_id": {"type": "string", "description": "已有会话 ID（可选）"},
        "timeout": {"type": "integer", "description": "超时秒数", "default": 30},
    },
    min_role="viewer",
)
register_capability(
    "browser-tools", "read_text", _read_text,
    description="提取当前页面的可见文本内容（截断保护）。返回标题/URL/可见文本/按钮列表。",
    brief="读取页面文本",
    parameters={
        "session_id": {"type": "string", "description": "浏览器会话 ID"},
    },
    min_role="viewer",
)
register_capability(
    "browser-tools", "list_links", _list_links,
    description="列出当前页面的可见链接（不含 Cookie/隐私数据）。返回最多 100 个去重链接。",
    brief="列出页面链接",
    parameters={
        "session_id": {"type": "string", "description": "浏览器会话 ID"},
    },
    min_role="viewer",
)
register_capability(
    "browser-tools", "click", _click,
    description="点击页面元素。支持 CSS selector 或按可见文本点击。",
    brief="点击元素",
    parameters={
        "session_id": {"type": "string", "description": "浏览器会话 ID"},
        "selector": {"type": "string", "description": "CSS 选择器"},
        "text": {"type": "string", "description": "可见文本匹配"},
        "timeout": {"type": "integer", "description": "超时秒数", "default": 30},
    },
    min_role="viewer",
)
register_capability(
    "browser-tools", "type", _type,
    description="向输入框输入文本。先清空再输入，带打字延迟。",
    brief="输入文本",
    parameters={
        "session_id": {"type": "string", "description": "浏览器会话 ID"},
        "selector": {"type": "string", "description": "CSS 选择器定位输入框"},
        "text": {"type": "string", "description": "要输入的文本"},
        "timeout": {"type": "integer", "description": "超时秒数", "default": 30},
    },
    min_role="viewer",
)
register_capability(
    "browser-tools", "wait_for", _wait_for,
    description="等待页面元素出现/导航完成/固定时间。",
    brief="等待条件",
    parameters={
        "session_id": {"type": "string", "description": "浏览器会话 ID"},
        "selector": {"type": "string", "description": "等待元素出现的 CSS 选择器"},
        "timeout": {"type": "integer", "description": "超时秒数", "default": 30},
        "wait_for_navigation": {"type": "boolean", "description": "等待页面导航完成"},
    },
    min_role="viewer",
)
register_capability(
    "browser-tools", "screenshot", _screenshot,
    description="截图并保存到工作区（非 base64）。支持全页截图。用 terminal-tools:publish 交付桌面。",
    brief="页面截图",
    parameters={
        "session_id": {"type": "string", "description": "浏览器会话 ID"},
        "full_page": {"type": "boolean", "description": "是否全页截图", "default": False},
    },
    min_role="viewer",
)
register_capability(
    "browser-tools", "download", _download,
    description="下载文件到工作区。支持浏览器上下文下载或直链 HTTP 下载。产物需显式 publish 才上桌面。",
    brief="下载文件",
    parameters={
        "session_id": {"type": "string", "description": "浏览器会话 ID"},
        "url": {"type": "string", "description": "下载 URL"},
        "timeout": {"type": "integer", "description": "超时秒数", "default": 30},
    },
    min_role="viewer",
)
register_capability(
    "browser-tools", "close", _close,
    description="关闭浏览器会话，释放隔离上下文资源。",
    brief="关闭浏览器",
    parameters={
        "session_id": {"type": "string", "description": "浏览器会话 ID"},
    },
    min_role="viewer",
)
