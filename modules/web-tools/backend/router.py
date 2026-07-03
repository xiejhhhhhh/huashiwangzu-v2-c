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
_MAX_QUERY_CHARS = 500
_MAX_URL_CHARS = 2048
_MAX_TITLE_CHARS = 500
_MAX_SEARCH_TITLE_CHARS = 300
_MAX_SEARCH_SNIPPET_CHARS = 1000
_MAX_SEARCH_URL_CHARS = 2048
_TEXT_CONTENT_MARKERS = ("text", "html", "json", "xml", "javascript", "x-www-form-urlencoded")
_BINARY_CONTENT_MARKERS = ("application/octet-stream", "application/pdf", "image/", "audio/", "video/")

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
        raise ValidationError(str(result.get("error") or "Web tool failed"))
    return ApiResponse(data=result)


def _bounded_int(value: Any, default: int, minimum: int, maximum: int, name: str) -> tuple[int | None, str | None]:
    if value is None:
        return default, None
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return None, f"{name} must be an integer"
    if parsed < minimum or parsed > maximum:
        return None, f"{name} must be between {minimum} and {maximum}"
    return parsed, None


def _trim_text(value: Any, max_chars: int) -> str:
    text = str(value or "").strip()
    if len(text) <= max_chars:
        return text
    return text[:max_chars]


def _is_binary_content_type(content_type: str) -> bool:
    ct = content_type.lower()
    if not ct:
        return False
    if any(marker in ct for marker in _TEXT_CONTENT_MARKERS):
        return False
    return any(marker in ct for marker in _BINARY_CONTENT_MARKERS)


def _decode_content(content: bytes, encoding: str | None) -> str:
    candidates = [encoding, "utf-8", "gb18030", "latin-1"]
    for candidate in candidates:
        if not candidate:
            continue
        try:
            return content.decode(candidate)
        except (LookupError, UnicodeDecodeError):
            continue
    return content.decode("utf-8", errors="replace")


async def _cap_search(params: dict, caller: str) -> dict:
    """Search the web via DuckDuckGo Search (no API key, uses ddgs)."""
    query = (params.get("query") or "").strip()
    top_k, top_k_error = _bounded_int(params.get("top_k"), 8, 1, 20, "top_k")
    if top_k_error:
        return _err({"results": []}, top_k_error)
    if not query:
        return _err({"results": []}, "query is required")
    if len(query) > _MAX_QUERY_CHARS:
        return _err({"results": []}, f"query too long ({len(query)} chars > {_MAX_QUERY_CHARS})")

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
            raw_url = _trim_text(r.get("href", ""), _MAX_SEARCH_URL_CHARS)
            parsed_url = urllib.parse.urlsplit(raw_url)
            if parsed_url.scheme not in {"http", "https"} or parsed_url.username or parsed_url.password:
                continue
            results.append({
                "title": _trim_text(r.get("title", ""), _MAX_SEARCH_TITLE_CHARS),
                "url": raw_url,
                "snippet": _trim_text(r.get("body", ""), _MAX_SEARCH_SNIPPET_CHARS),
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
    if len(url) > _MAX_URL_CHARS:
        return _err(
            {"url": url[:_MAX_URL_CHARS], "title": "", "text": "", "truncated": False},
            f"url too long ({len(url)} chars > {_MAX_URL_CHARS})",
        )

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
        *,
        stream: bool = False,
    ) -> tuple[httpx.Response, str]:
        current_url = start_url
        for _ in range(8):
            try:
                current_url = validate_safe_url(current_url)
            except ValidationError as exc:
                raise ValidationError(exc.message) from exc
            request = client.build_request(method, current_url, timeout=10 if method == "HEAD" else _FETCH_TIMEOUT)
            resp = await client.send(request, stream=stream)
            if resp.is_redirect:
                location = resp.headers.get("location")
                await resp.aclose()
                if not location:
                    raise ValidationError("redirect target missing")
                current_url = urllib.parse.urljoin(current_url, location)
                continue
            return resp, current_url
        raise ValidationError("too many redirects")

    try:
        async with httpx.AsyncClient(**client_kwargs) as client:
            # Head request first to check content type and size
            head_resp, _ = await _request_checked(client, "HEAD", url)
            ct = (head_resp.headers.get("content-type") or "").lower()
            cl = head_resp.headers.get("content-length")
            if cl:
                try:
                    content_length = int(cl)
                except ValueError:
                    content_length = None
                if content_length is not None and content_length > _MAX_CONTENT_LENGTH:
                    return _err(
                        {"url": url, "title": "", "text": "", "truncated": False},
                        f"content too large ({content_length} bytes > 5MB)",
                    )
            if _is_binary_content_type(ct):
                return _err(
                    {"url": url, "title": "", "text": "", "truncated": False},
                    f"blocked binary content type: {ct}",
                )

            resp, fetched_url = await _request_checked(client, "GET", url, stream=True)
            try:
                resp.raise_for_status()
                get_ct = (resp.headers.get("content-type") or "").lower()
                if _is_binary_content_type(get_ct):
                    return _err(
                        {"url": fetched_url, "title": "", "text": "", "truncated": False},
                        f"blocked binary content type: {get_ct}",
                    )

                chunks = bytearray()
                async for chunk in resp.aiter_bytes():
                    if len(chunks) + len(chunk) > _MAX_CONTENT_LENGTH:
                        return _err(
                            {"url": fetched_url, "title": "", "text": "", "truncated": False},
                            f"content too large (> {_MAX_CONTENT_LENGTH} bytes)",
                        )
                    chunks.extend(chunk)
                content = bytes(chunks)
            finally:
                await resp.aclose()
    except ValidationError as exc:
        return _err({"url": url, "title": "", "text": "", "truncated": False}, exc.message)
    except httpx.TimeoutException:
        return _err({"url": url, "title": "", "text": "", "truncated": False}, "request timed out")
    except Exception as exc:
        return _err({"url": url, "title": "", "text": "", "truncated": False}, f"fetch failed: {exc}")

    get_ct = (resp.headers.get("content-type") or "").lower()
    if get_ct and "html" not in get_ct and "xml" not in get_ct:
        text = _decode_content(content, resp.charset_encoding)
        text = _re.sub(r'\s+', ' ', text).strip()
        truncated = False
        if len(text) > max_chars:
            text = text[:max_chars]
            truncated = True
        return _ok({"url": fetched_url, "title": "", "text": text, "truncated": truncated, "error": None})

    # Parse HTML/XML-like content
    try:
        tree = lxml_html.fromstring(content)
    except Exception as exc:
        return _err({"url": fetched_url, "title": "", "text": "", "truncated": False}, f"parse failed: {exc}")

    # Extract title
    title = ""
    title_el = tree.find(".//title")
    if title_el is not None and title_el.text:
        title = _trim_text(title_el.text, _MAX_TITLE_CHARS)

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

    return _ok({"url": fetched_url, "title": title, "text": text, "truncated": truncated, "error": None})


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
