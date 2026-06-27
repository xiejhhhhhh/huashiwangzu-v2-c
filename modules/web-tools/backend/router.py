"""FastAPI router for web-tools module.

Exposes 2 cross-module capabilities:
  web-tools:search  — DuckDuckGo HTML search (no API key)
  web-tools:fetch   — Fetch web page content (no API key, SSRF protected)
"""
import logging
import os
import re as _re
import urllib.parse

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from app.core.url_safety import validate_safe_url
from app.core.exceptions import ValidationError
from app.middleware.auth import require_permission
from app.models.user import User
from app.schemas.common import ApiResponse
from app.services.module_registry import register_capability

logger = logging.getLogger("v2.web-tools")

router = APIRouter(prefix="/api/web-tools", tags=["web-tools"])

# ── Configuration ───────────────────────────────────────────────────────
_SEARCH_TIMEOUT = 10
_FETCH_TIMEOUT = 15
_MAX_FETCH_CHARS = 8000
_MAX_CONTENT_LENGTH = 5 * 1024 * 1024  # 5MB

# SSRF block list — internal/private IP ranges
_SSRF_BLOCKED = (
    "localhost", "127.", "10.", "172.16.", "172.17.", "172.18.", "172.19.",
    "172.20.", "172.21.", "172.22.", "172.23.", "172.24.", "172.25.",
    "172.26.", "172.27.", "172.28.", "172.29.", "172.30.", "172.31.",
    "192.168.", "169.254.", "0.0.0.0", "::1", "fc00:", "fe80:",
)

# Proxy from env: WEB_TOOLS_PROXY=http://127.0.0.1:4780
# Default to ClashX proxy on macOS (common local proxy)
_PROXY_URL = os.environ.get("WEB_TOOLS_PROXY") or "http://127.0.0.1:4780"

UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/120.0.0.0 Safari/537.36"
)
_HEADERS = {
    "User-Agent": UA,
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
}


def _check_ssrf(url: str) -> str | None:
    """Check URL for SSRF risks. Returns error message or None if safe."""
    parsed = urllib.parse.urlparse(url)
    if parsed.scheme not in ("http", "https"):
        return "blocked non-http(s) protocol"
    hostname = parsed.hostname or ""
    hostname_lower = hostname.lower()
    for prefix in _SSRF_BLOCKED:
        if hostname_lower.startswith(prefix) or hostname_lower == prefix.rstrip("."):
            return "blocked internal address"
    return None


async def _cap_search(params: dict, caller: str) -> dict:
    """Search the web via DuckDuckGo Search (no API key, uses ddgs)."""
    query = (params.get("query") or "").strip()
    top_k = int(params.get("top_k", 8))
    if not query:
        return {"results": [], "error": "query is required"}
    top_k = max(1, min(top_k, 20))

    import asyncio

    def _do_search(proxy_url: str | None) -> list[dict]:
        from ddgs import DDGS
        kwargs = {"timeout": _SEARCH_TIMEOUT}
        if proxy_url:
            kwargs["proxy"] = proxy_url
        with DDGS(**kwargs) as ddgs:
            rows = ddgs.text(
                query,
                max_results=top_k,
                region="cn-zh",
                safesearch="moderate",
            )
            return list(rows)

    # Try proxy first, then direct
    proxies_to_try = [_PROXY_URL, None]
    last_error = None
    for proxy in proxies_to_try:
        try:
            rows = await asyncio.to_thread(_do_search, proxy)
        except Exception as exc:
            last_error = exc
            logger.warning("DDGS search attempt (proxy=%s) failed: %s", proxy, exc)
            continue
        results = []
        for r in rows:
            results.append({
                "title": r.get("title", ""),
                "url": r.get("href", ""),
                "snippet": r.get("body", ""),
            })
        return {"results": results, "error": None}

    return {"results": [], "error": f"search failed: {last_error}"}


async def _cap_fetch(params: dict, caller: str) -> dict:
    """Fetch and extract text content from a web page (no API key)."""
    url = (params.get("url") or "").strip()
    max_chars = int(params.get("max_chars", _MAX_FETCH_CHARS))
    if not url:
        return {"url": url, "title": "", "text": "", "truncated": False, "error": "url is required"}

    # SSRF check via public helper
    try:
        url = validate_safe_url(url)
    except ValidationError as exc:
        return {"url": url, "title": "", "text": "", "truncated": False, "error": exc.message}

    import httpx
    from lxml import html as lxml_html

    client_kwargs = {
        "timeout": _FETCH_TIMEOUT,
        "follow_redirects": True,
        "headers": _HEADERS,
    }
    if _PROXY_URL:
        client_kwargs["proxy"] = httpx.Proxy(url=_PROXY_URL)

    try:
        async with httpx.AsyncClient(**client_kwargs) as client:
            # Head request first to check content type and size
            head_resp = await client.head(url, timeout=10)
            ct = (head_resp.headers.get("content-type") or "").lower()
            cl = head_resp.headers.get("content-length")
            if cl and int(cl) > _MAX_CONTENT_LENGTH:
                return {
                    "url": url, "title": "", "text": "",
                    "truncated": False,
                    "error": f"content too large ({cl} bytes > 5MB)",
                }
            if "text" not in ct and "html" not in ct and "json" not in ct and "xml" not in ct:
                for bt in ("application/octet-stream", "application/pdf", "image/", "audio/", "video/"):
                    if bt in ct:
                        return {
                            "url": url, "title": "", "text": "",
                            "truncated": False,
                            "error": f"blocked binary content type: {ct}",
                        }

            resp = await client.get(url)
            resp.raise_for_status()
    except httpx.TimeoutException:
        return {"url": url, "title": "", "text": "", "truncated": False, "error": "request timed out"}
    except Exception as exc:
        return {"url": url, "title": "", "text": "", "truncated": False, "error": f"fetch failed: {exc}"}

    # Parse HTML
    try:
        tree = lxml_html.fromstring(resp.content)
    except Exception as exc:
        return {"url": url, "title": "", "text": "", "truncated": False, "error": f"parse failed: {exc}"}

    # Extract title
    title = ""
    title_el = tree.find(".//title")
    if title_el is not None and title_el.text:
        title = title_el.text.strip()

    # Remove unwanted elements
    for tag in ("script", "style", "nav", "footer", "header", "aside", "noscript",
                "iframe", "form", "button", "input", "select", "textarea"):
        for el in list(tree.iter(tag)):
            try:
                el.drop_tree()
            except Exception:
                pass

    # Get text from body
    body = tree.find(".//body")
    text = ""
    if body is not None:
        text = body.text_content().strip()
        text = _re.sub(r'\s+', ' ', text)
        text = _re.sub(r'\n\s*\n', '\n', text)

    truncated = False
    if len(text) > max_chars:
        text = text[:max_chars]
        truncated = True

    return {"url": url, "title": title, "text": text, "truncated": truncated, "error": None}


# ── HTTP endpoints for direct testing ──────────────────────────────────

class SearchRequest(BaseModel):
    query: str
    top_k: int = 8


class FetchRequest(BaseModel):
    url: str
    max_chars: int = _MAX_FETCH_CHARS


@router.get("/health")
async def health():
    return ApiResponse(data={"module": "web-tools", "status": "ok"})


@router.post("/search")
async def http_search(
    body: SearchRequest,
    user: User = Depends(require_permission("viewer")),
):
    result = await _cap_search(body.model_dump(), f"user:{user.id}")
    return ApiResponse(data=result)


@router.post("/fetch")
async def http_fetch(
    body: FetchRequest,
    user: User = Depends(require_permission("viewer")),
):
    result = await _cap_fetch(body.model_dump(), f"user:{user.id}")
    return ApiResponse(data=result)


# ── Register capabilities with framework ──────────────────────────────

register_capability(
    "web-tools", "search", _cap_search,
    description="联网搜索网页,返回标题/链接/摘要(无需API key)。基于 DuckDuckGo HTML 端点。",
    brief="联网搜索信息",
    parameters={
        "type": "object",
        "properties": {
            "query": {"type": "string", "description": "搜索关键词"},
            "top_k": {"type": "integer", "description": "返回结果数量（默认8，最大20）", "default": 8},
        },
        "required": ["query"],
    },
    min_role="viewer",
)

register_capability(
    "web-tools", "fetch", _cap_fetch,
    description="抓取指定网址正文文本(无需API key)。自动过滤 script/style/nav/footer。含SSRF防护，拒绝内网地址。",
    brief="读取网页正文",
    parameters={
        "type": "object",
        "properties": {
            "url": {"type": "string", "description": "目标网址"},
            "max_chars": {"type": "integer", "description": "最大返回字符数（默认8000）", "default": 8000},
        },
        "required": ["url"],
    },
    min_role="viewer",
)
