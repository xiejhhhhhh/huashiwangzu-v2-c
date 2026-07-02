"""FastAPI router for web-tools module.

Exposes 2 cross-module capabilities:
  web-tools:search  — DuckDuckGo HTML search (no API key)
  web-tools:fetch   — Fetch web page content (no API key, SSRF protected)
"""
import logging
import os
import re as _re
import urllib.parse
from typing import Any, Literal

from app.core.exceptions import ValidationError
from app.core.url_safety import validate_safe_url
from app.middleware.auth import require_permission
from app.models.user import User
from app.schemas.common import ApiResponse
from app.services.module_registry import register_capability
from fastapi import APIRouter, Depends
from pydantic import BaseModel

logger = logging.getLogger("v2.web-tools")

router = APIRouter(prefix="/api/web-tools", tags=["web-tools"])

# ── Configuration ───────────────────────────────────────────────────────
_SEARCH_TIMEOUT = 10
_FETCH_TIMEOUT = 15
_MAX_FETCH_CHARS = 8000
_MAX_CONTENT_LENGTH = 5 * 1024 * 1024  # 5MB

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


def _ok(data: dict[str, Any]) -> dict[str, Any]:
    return {"success": True, **data}


def _err(data: dict[str, Any], message: str) -> dict[str, Any]:
    return {"success": False, **data, "error": message}


def _web_response(result: dict[str, Any]) -> ApiResponse[dict[str, Any]]:
    if result.get("success") is False:
        return ApiResponse(success=False, data=result, error=str(result.get("error") or "Web tool failed"))
    return ApiResponse(data=result)


def _bounded_int(value: Any, default: int, minimum: int, maximum: int, name: str) -> tuple[int | None, str | None]:
    if value is None:
        return default, None
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return None, f"{name} must be an integer"
    return max(minimum, min(parsed, maximum)), None


async def _cap_search(params: dict, caller: str) -> dict:
    """Search the web via DuckDuckGo Search (no API key, uses ddgs)."""
    query = (params.get("query") or "").strip()
    top_k, top_k_error = _bounded_int(params.get("top_k"), 8, 1, 20, "top_k")
    if top_k_error:
        return _err({"results": []}, top_k_error)
    if not query:
        return _err({"results": []}, "query is required")

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
        return _ok({"results": results, "error": None})

    return _err({"results": []}, f"search failed: {last_error}")


async def _cap_fetch(params: dict, caller: str) -> dict:
    """Fetch and extract text content from a web page (no API key)."""
    url = (params.get("url") or "").strip()
    max_chars, max_chars_error = _bounded_int(params.get("max_chars"), _MAX_FETCH_CHARS, 1, _MAX_FETCH_CHARS, "max_chars")
    if max_chars_error:
        return _err({"url": url, "title": "", "text": "", "truncated": False}, max_chars_error)
    if not url:
        return _err({"url": url, "title": "", "text": "", "truncated": False}, "url is required")

    # SSRF check via public helper
    try:
        url = validate_safe_url(url)
    except ValidationError as exc:
        return _err({"url": url, "title": "", "text": "", "truncated": False}, exc.message)

    import httpx
    from lxml import html as lxml_html

    client_kwargs = {
        "timeout": _FETCH_TIMEOUT,
        "follow_redirects": False,
        "headers": _HEADERS,
    }
    if _PROXY_URL:
        client_kwargs["proxy"] = httpx.Proxy(url=_PROXY_URL)

    async def _request_checked(
        client: httpx.AsyncClient,
        method: Literal["HEAD", "GET"],
        start_url: str,
    ) -> httpx.Response:
        current_url = start_url
        for _ in range(8):
            try:
                current_url = validate_safe_url(current_url)
            except ValidationError as exc:
                raise ValidationError(exc.message) from exc
            resp = await client.request(method, current_url, timeout=10 if method == "HEAD" else _FETCH_TIMEOUT)
            if resp.is_redirect:
                location = resp.headers.get("location")
                if not location:
                    raise ValidationError("redirect target missing")
                current_url = urllib.parse.urljoin(current_url, location)
                continue
            return resp
        raise ValidationError("too many redirects")

    try:
        async with httpx.AsyncClient(**client_kwargs) as client:
            # Head request first to check content type and size
            head_resp = await _request_checked(client, "HEAD", url)
            ct = (head_resp.headers.get("content-type") or "").lower()
            cl = head_resp.headers.get("content-length")
            if cl and int(cl) > _MAX_CONTENT_LENGTH:
                return _err(
                    {"url": url, "title": "", "text": "", "truncated": False},
                    f"content too large ({cl} bytes > 5MB)",
                )
            if "text" not in ct and "html" not in ct and "json" not in ct and "xml" not in ct:
                for bt in ("application/octet-stream", "application/pdf", "image/", "audio/", "video/"):
                    if bt in ct:
                        return _err(
                            {"url": url, "title": "", "text": "", "truncated": False},
                            f"blocked binary content type: {ct}",
                        )

            resp = await _request_checked(client, "GET", url)
            resp.raise_for_status()
    except ValidationError as exc:
        return _err({"url": url, "title": "", "text": "", "truncated": False}, exc.message)
    except httpx.TimeoutException:
        return _err({"url": url, "title": "", "text": "", "truncated": False}, "request timed out")
    except Exception as exc:
        return _err({"url": url, "title": "", "text": "", "truncated": False}, f"fetch failed: {exc}")

    # Parse HTML
    try:
        tree = lxml_html.fromstring(resp.content)
    except Exception as exc:
        return _err({"url": url, "title": "", "text": "", "truncated": False}, f"parse failed: {exc}")

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

    return _ok({"url": url, "title": title, "text": text, "truncated": truncated, "error": None})


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
    return _web_response(result)


@router.post("/fetch")
async def http_fetch(
    body: FetchRequest,
    user: User = Depends(require_permission("viewer")),
):
    result = await _cap_fetch(body.model_dump(), f"user:{user.id}")
    return _web_response(result)


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
