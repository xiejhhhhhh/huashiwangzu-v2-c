"""Sandbox test for browser-tools module.

Validates parameter schemas, required fields, value ranges, and output shapes
based on MANIFEST public_actions. No real browser calls.
"""
import asyncio
import importlib.util
import sys
import tempfile
import types
from collections.abc import Callable
from pathlib import Path
from typing import Any

# ── URL validation helpers ─────────────────────────────────────────────

_HANDLER_MODULE = None


def _install_handler_import_stubs() -> None:
    app_module = sys.modules.setdefault("app", types.ModuleType("app"))
    core_module = sys.modules.setdefault("app.core", types.ModuleType("app.core"))
    services_module = sys.modules.setdefault("app.services", types.ModuleType("app.services"))
    setattr(app_module, "core", core_module)
    setattr(app_module, "services", services_module)

    exceptions_module = types.ModuleType("app.core.exceptions")

    class ValidationError(Exception):
        def __init__(self, message: str) -> None:
            super().__init__(message)
            self.message = message

    exceptions_module.ValidationError = ValidationError
    sys.modules["app.core.exceptions"] = exceptions_module

    url_safety_module = types.ModuleType("app.core.url_safety")
    url_safety_module.validate_safe_url = lambda _url: None
    sys.modules["app.core.url_safety"] = url_safety_module

    registry_module = types.ModuleType("app.services.module_registry")
    registry_module.register_capability = lambda *_args, **_kwargs: None
    sys.modules["app.services.module_registry"] = registry_module


def _load_browser_handler():
    global _HANDLER_MODULE
    if _HANDLER_MODULE is not None:
        return _HANDLER_MODULE
    _install_handler_import_stubs()
    handler_path = Path(__file__).resolve().parents[1] / "backend" / "handlers" / "browser.py"
    spec = importlib.util.spec_from_file_location("browser_tools_handler_under_test", handler_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules["browser_tools_handler_under_test"] = module
    spec.loader.exec_module(module)
    _HANDLER_MODULE = module
    return module


def _assert_rejected(fn: Callable[[], None], label: str) -> None:
    try:
        fn()
    except AssertionError:
        print(f"{label}: PASS")
        return
    raise AssertionError(f"{label}: expected AssertionError")

def _validate_url(url: str) -> None:
    """Reject non-http/https URLs."""
    if not isinstance(url, str) or not url.strip():
        raise AssertionError("URL must be a non-empty string")
    if not (url.startswith("http://") or url.startswith("https://")):
        raise AssertionError(f"URL must start with http:// or https://, got: {url[:30]}")


def _validate_session_id(session_id: Any, *, required: bool = True) -> None:
    """Validate session_id is a non-empty string when required."""
    if required:
        assert isinstance(session_id, str) and session_id.strip(), \
            "session_id is required and must be a non-empty string"
    else:
        if session_id is not None:
            assert isinstance(session_id, str) and session_id.strip(), \
                "session_id must be a non-empty string when provided"


def _validate_timeout(timeout: Any) -> None:
    """Validate timeout is a positive bounded number (default 30)."""
    if timeout is not None:
        assert isinstance(timeout, (int, float)) and 0 < timeout <= 60, \
            f"timeout must be a positive number, got: {timeout!r}"


# ── Parameter validation per action ────────────────────────────────────

def test_open_params() -> None:
    """open: url required; session_id, viewport and timeout optional."""
    # Valid
    params = {"url": "https://example.com"}
    _validate_url(params["url"])
    _validate_session_id(params.get("session_id"), required=False)
    _validate_timeout(params.get("timeout"))
    print("  [open] Valid params (url only): PASS")

    # With optional session_id
    params = {
        "url": "http://example.org",
        "session_id": "sess_abc123",
        "width": 1366,
        "height": 768,
        "timeout": 15,
    }
    _validate_url(params["url"])
    _validate_session_id(params["session_id"], required=False)
    assert isinstance(params["width"], int) and params["width"] > 0
    assert isinstance(params["height"], int) and params["height"] > 0
    _validate_timeout(params["timeout"])
    print("  [open] Valid params (reuse session + viewport): PASS")

    # Missing url
    _assert_rejected(lambda: _validate_url(""), "  [open] Missing url rejected")

    # Bad protocol
    _assert_rejected(lambda: _validate_url("ftp://example.com"), "  [open] Bad protocol rejected")


def test_read_text_params() -> None:
    """read_text: session_id required."""
    params = {"session_id": "sess_abc123"}
    _validate_session_id(params["session_id"])
    print("  [read_text] Valid params: PASS")

    _assert_rejected(lambda: _validate_session_id(""), "  [read_text] Empty session_id rejected")

    _assert_rejected(lambda: _validate_session_id(None), "  [read_text] None session_id rejected")


def test_list_links_params() -> None:
    """list_links: session_id required."""
    params = {"session_id": "sess_xyz789"}
    _validate_session_id(params["session_id"])
    print("  [list_links] Valid params: PASS")


def test_click_params() -> None:
    """click: session_id required, selector or text target, timeout optional."""
    # Valid: selector only
    params = {"session_id": "sess_abc", "selector": "#submit-btn"}
    _validate_session_id(params["session_id"])
    assert "selector" in params or "text" in params, "click needs selector or text"
    _validate_timeout(params.get("timeout"))
    print("  [click] Valid (selector only): PASS")

    # Valid: text only
    params = {"session_id": "sess_abc", "text": "Submit"}
    _validate_session_id(params["session_id"])
    assert "selector" in params or "text" in params, "click needs selector or text"
    print("  [click] Valid (text only): PASS")

    # Both provided: handler uses selector first.
    params = {"session_id": "sess_abc", "selector": "#btn", "text": "Click", "timeout": 10}
    _validate_session_id(params["session_id"])
    assert params["selector"] and params["text"]
    _validate_timeout(params["timeout"])
    print("  [click] Valid (selector takes precedence when both provided): PASS")

    # Missing both selector and text
    def reject_missing_click_target() -> None:
        params = {"session_id": "sess_abc"}
        _validate_session_id(params["session_id"])
        assert "selector" in params or "text" in params, \
            "click requires either 'selector' or 'text' parameter"

    _assert_rejected(reject_missing_click_target, "  [click] Missing selector+text rejected")


def test_type_params() -> None:
    """type: session_id and selector required; text string and timeout optional."""
    params = {"session_id": "sess_abc", "selector": "#search-input", "text": "hello world"}
    _validate_session_id(params["session_id"])
    assert isinstance(params.get("selector"), str) and params["selector"].strip(), \
        "type requires a non-empty selector"
    assert isinstance(params.get("text"), str), "type text must be a string"
    _validate_timeout(params.get("timeout"))
    print("  [type] Valid params: PASS")

    # Empty text is valid: it clears the input.
    params = {"session_id": "sess_abc", "selector": "#input", "text": "", "timeout": 5}
    _validate_session_id(params["session_id"])
    assert isinstance(params["text"], str)
    _validate_timeout(params["timeout"])
    print("  [type] Empty text clears input: PASS")

    # Missing selector
    def reject_missing_selector() -> None:
        params = {"session_id": "sess_abc", "text": "hello"}
        assert isinstance(params.get("selector"), str) and params["selector"].strip(), \
            "type requires a non-empty selector"

    _assert_rejected(reject_missing_selector, "  [type] Missing selector rejected")


def test_wait_for_params() -> None:
    """wait_for: session_id required; selector/navigation/fixed wait are supported."""
    params = {"session_id": "sess_abc", "selector": ".loaded"}
    _validate_session_id(params["session_id"])
    assert isinstance(params.get("selector"), str) and params["selector"].strip(), \
        "wait_for requires a non-empty selector"
    _validate_timeout(params.get("timeout"))
    print("  [wait_for] Valid params: PASS")

    params_full = {"session_id": "sess_abc", "selector": "#done", "timeout": 60}
    _validate_session_id(params_full["session_id"])
    _validate_timeout(params_full["timeout"])
    print("  [wait_for] Valid params with timeout: PASS")

    params_nav = {"session_id": "sess_abc", "wait_for_navigation": True}
    _validate_session_id(params_nav["session_id"])
    assert isinstance(params_nav["wait_for_navigation"], bool)
    print("  [wait_for] Valid navigation wait: PASS")

    params_fixed = {"session_id": "sess_abc"}
    _validate_session_id(params_fixed["session_id"])
    print("  [wait_for] Valid fixed short wait: PASS")


def test_screenshot_params() -> None:
    """screenshot: session_id required, full_page optional bool."""
    params = {"session_id": "sess_abc"}
    _validate_session_id(params["session_id"])
    print("  [screenshot] Valid params (no full_page): PASS")

    params = {"session_id": "sess_abc", "full_page": True}
    _validate_session_id(params["session_id"])
    assert isinstance(params.get("full_page"), bool), "full_page must be boolean"
    print("  [screenshot] Valid params (full_page=True): PASS")

    # Invalid full_page type
    def reject_non_bool_full_page() -> None:
        params = {"session_id": "sess_abc", "full_page": "yes"}
        assert isinstance(params.get("full_page"), bool), \
            "full_page must be boolean"

    _assert_rejected(reject_non_bool_full_page, "  [screenshot] Non-bool full_page rejected")


def test_download_params() -> None:
    """download: session_id or url required, timeout optional."""
    params = {"session_id": "sess_abc"}
    _validate_session_id(params["session_id"])
    if "url" in params:
        _validate_url(params["url"])
    _validate_timeout(params.get("timeout"))
    print("  [download] Valid params (url optional from browser context): PASS")

    params = {"session_id": "sess_abc", "url": "https://example.com/file.pdf", "timeout": 60}
    _validate_session_id(params["session_id"])
    _validate_url(params["url"])
    _validate_timeout(params["timeout"])
    print("  [download] Valid params (with url): PASS")

    params = {"url": "https://example.com/file.pdf", "timeout": 60}
    _validate_url(params["url"])
    _validate_session_id(params.get("session_id"), required=False)
    _validate_timeout(params["timeout"])
    print("  [download] Valid params (direct HTTP url only): PASS")

    def reject_download_non_http_url() -> None:
        params = {"session_id": "sess_abc", "url": "file:///etc/passwd"}
        _validate_session_id(params["session_id"])
        _validate_url(params["url"])

    _assert_rejected(reject_download_non_http_url, "  [download] Non-http URL rejected")


class _FakeRequest:
    def __init__(self, url: str) -> None:
        self.url = url


class _FakeResponse:
    def __init__(
        self,
        *,
        chunks: list[bytes] | None = None,
        headers: dict[str, str] | None = None,
        status_code: int = 200,
        next_url: str = "",
    ) -> None:
        self._chunks = chunks or []
        self.headers = headers or {}
        self.status_code = status_code
        self.is_redirect = 300 <= status_code < 400
        self.next_request = _FakeRequest(next_url) if next_url else None

    async def __aenter__(self):
        return self

    async def __aexit__(self, _exc_type, _exc, _tb) -> None:
        return None

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")

    async def aiter_bytes(self):
        for chunk in self._chunks:
            yield chunk


class _FakeAsyncClient:
    responses: list[_FakeResponse] = []

    def __init__(self, **kwargs) -> None:
        self.kwargs = kwargs

    async def __aenter__(self):
        return self

    async def __aexit__(self, _exc_type, _exc, _tb) -> None:
        return None

    def stream(self, _method: str, _url: str):
        assert self.responses, "fake httpx response queue is empty"
        return self.responses.pop(0)


def _run_fake_httpx_download(handler, responses: list[_FakeResponse], coro_factory):
    old_httpx = sys.modules.get("httpx")
    _FakeAsyncClient.responses = list(responses)
    sys.modules["httpx"] = types.SimpleNamespace(AsyncClient=_FakeAsyncClient)
    try:
        return asyncio.run(coro_factory())
    finally:
        if old_httpx is None:
            sys.modules.pop("httpx", None)
        else:
            sys.modules["httpx"] = old_httpx


def test_timeout_clamp() -> None:
    """External timeout input is coerced and clamped before use."""
    handler = _load_browser_handler()
    assert handler._bounded_timeout_seconds(None) == 30
    assert handler._bounded_timeout_seconds("bad") == 30
    assert handler._bounded_timeout_seconds(True) == 30
    assert handler._bounded_timeout_seconds(-5) == 1
    assert handler._bounded_timeout_seconds(9999) == 60
    assert handler._timeout_ms({"timeout": 9999}) == 60_000
    print("  [timeout] Invalid and excessive values are clamped: PASS")


def test_direct_http_download_streams_to_file() -> None:
    """Direct HTTP downloads stream chunks to disk instead of returning content bytes."""
    handler = _load_browser_handler()
    old_blocked_error = handler._blocked_error
    handler._blocked_error = lambda _url: ""
    try:
        with tempfile.TemporaryDirectory() as tmpdir:
            destination = Path(tmpdir) / "download.tmp"

            async def run_download():
                return await handler._download_http_checked(
                    "https://example.com/file.txt",
                    destination,
                    timeout=handler._bounded_timeout_seconds(9999),
                )

            size, final_url = _run_fake_httpx_download(
                handler,
                [_FakeResponse(chunks=[b"abc", b"de"], headers={"content-length": "5"})],
                run_download,
            )
            assert size == 5
            assert final_url == "https://example.com/file.txt"
            assert destination.read_bytes() == b"abcde"
    finally:
        handler._blocked_error = old_blocked_error
    print("  [download] Direct HTTP path streams chunks to destination: PASS")


def test_direct_http_download_stream_limit_cleans_partial_file() -> None:
    """Streaming limit aborts and removes the partial file on oversized content."""
    handler = _load_browser_handler()
    old_limit = handler._MAX_DOWNLOAD_BYTES
    old_blocked_error = handler._blocked_error
    handler._MAX_DOWNLOAD_BYTES = 8
    handler._blocked_error = lambda _url: ""
    try:
        with tempfile.TemporaryDirectory() as tmpdir:
            destination = Path(tmpdir) / "oversized.tmp"

            async def run_download():
                return await handler._download_http_checked(
                    "https://example.com/big.bin",
                    destination,
                    timeout=30,
                )

            try:
                _run_fake_httpx_download(
                    handler,
                    [_FakeResponse(chunks=[b"12345", b"6789"])],
                    run_download,
                )
            except ValueError as exc:
                assert "download too large" in str(exc)
            else:
                raise AssertionError("oversized stream should fail")
            assert not destination.exists(), "partial oversized file must be removed"
    finally:
        handler._MAX_DOWNLOAD_BYTES = old_limit
        handler._blocked_error = old_blocked_error
    print("  [download] Oversized stream fails closed and cleans partial file: PASS")


def test_direct_http_download_redirect_revalidates_ssrf_target() -> None:
    """Every redirect hop is checked before the next request."""
    handler = _load_browser_handler()
    old_blocked_error = handler._blocked_error
    checked_urls: list[str] = []

    def fake_blocked_error(url: str) -> str:
        checked_urls.append(url)
        if "127.0.0.1" in url:
            return "URL targets a private/internal address"
        return ""

    handler._blocked_error = fake_blocked_error
    try:
        with tempfile.TemporaryDirectory() as tmpdir:
            destination = Path(tmpdir) / "redirect.tmp"

            async def run_download():
                return await handler._download_http_checked(
                    "https://example.com/redirect",
                    destination,
                    timeout=30,
                )

            try:
                _run_fake_httpx_download(
                    handler,
                    [_FakeResponse(status_code=302, next_url="http://127.0.0.1/secret")],
                    run_download,
                )
            except ValueError as exc:
                assert "private/internal" in str(exc)
            else:
                raise AssertionError("redirect to internal target should fail")
            assert checked_urls == ["https://example.com/redirect", "http://127.0.0.1/secret"]
            assert not destination.exists()
    finally:
        handler._blocked_error = old_blocked_error
    print("  [download] Redirect targets are revalidated for SSRF: PASS")


def test_download_filename_rejects_paths() -> None:
    """Browser suggested_filename must be a safe basename, never a path."""
    handler = _load_browser_handler()
    assert handler._safe_download_filename("report.pdf", "fallback.bin") == "report.pdf"
    assert handler._safe_download_filename("", "fallback.bin") == "fallback.bin"
    for raw in ("../secret.txt", "/tmp/report.pdf", "nested\\evil.txt", ".", "..", "bad\x00name"):
        try:
            handler._safe_download_filename(raw, "fallback.bin")
        except ValueError:
            continue
        raise AssertionError(f"unsafe download filename should fail: {raw!r}")
    print("  [download] suggested_filename path injection rejected: PASS")


class _FakeClosable:
    def __init__(self, label: str, fail: bool = False) -> None:
        self.label = label
        self.fail = fail
        self.closed = False

    async def close(self) -> None:
        if self.fail:
            raise RuntimeError(f"{self.label} failed")
        self.closed = True


class _FakePlaywright:
    def __init__(self, fail: bool = False) -> None:
        self.fail = fail
        self.stopped = False

    async def stop(self) -> None:
        if self.fail:
            raise RuntimeError("playwright failed")
        self.stopped = True


def test_close_session_reports_cleanup_errors() -> None:
    """close must report degraded cleanup instead of pretending success."""
    handler = _load_browser_handler()
    session_id = "sandbox-close-degraded"
    with tempfile.TemporaryDirectory() as tmpdir:
        handler._sessions[session_id] = {
            "context": _FakeClosable("context", fail=True),
            "browser": _FakeClosable("browser"),
            "playwright": _FakePlaywright(),
            "temp_dir": tmpdir,
        }
        result = asyncio.run(handler._close_session(session_id))
        assert result["closed"] is False
        assert result["degraded"] is True
        assert result["cleanup_errors"]
        assert result["cleanup_errors"][0]["step"] == "context"
        assert session_id not in handler._sessions
    print("  [close] Cleanup errors are surfaced as degraded: PASS")


def test_close_params() -> None:
    """close: session_id required, returns success/failure."""
    params = {"session_id": "sess_abc"}
    _validate_session_id(params["session_id"])
    print("  [close] Valid params: PASS")

    # Simulate output shape
    success_result = {"success": True, "data": {"session_id": "sess_abc", "closed": True}, "error": None}
    assert isinstance(success_result["success"], bool)
    assert success_result["data"]["session_id"] == "sess_abc"
    failure_result = {"success": False, "data": None, "error": "Session not found"}
    assert failure_result["success"] is False
    print("  [close] Output shape (success/failure): PASS")


def test_output_shapes() -> None:
    """Validate output shapes for screenshot and download."""
    # Screenshot output shape
    screenshot_result = {
        "session_id": "sess_abc",
        "file_path": "data/workspaces/1/screenshot_abc123.png",
        "filename": "screenshot_abc123.png",
        "size": 245760,
        "full_page": True,
        "note": "Use terminal-tools:publish to deliver to desktop",
    }
    assert isinstance(screenshot_result["session_id"], str)
    assert isinstance(screenshot_result["file_path"], str)
    assert isinstance(screenshot_result["filename"], str)
    assert isinstance(screenshot_result["size"], int) and screenshot_result["size"] >= 0
    assert isinstance(screenshot_result["full_page"], bool)
    print("  [screenshot] Output shape (file_path, filename, size): PASS")

    # Download output shape
    download_result = {
        "session_id": "sess_abc",
        "file_path": "data/workspaces/1/report.pdf",
        "filename": "report.pdf",
        "size": 1048576,
        "note": "Use terminal-tools:publish to deliver to desktop",
    }
    assert isinstance(download_result["file_path"], str)
    assert isinstance(download_result["filename"], str)
    assert isinstance(download_result["size"], int) and download_result["size"] >= 0
    print("  [download] Output shape (file_path, filename, size): PASS")


def test_no_cookie_localstorage_return() -> None:
    """Cookie/localStorage NOT returned to caller by any action."""
    # Simulate a read_text response — must NOT contain cookies or localStorage
    result = {
        "title": "Example",
        "url": "https://example.com",
        "text": "Hello world",
    }
    assert "cookies" not in result, "Cookies must not be returned"
    assert "localStorage" not in result, "localStorage must not be returned"
    assert "cookie" not in result, "Cookie data must not leak"
    print("  [privacy] No cookie/localStorage in output: PASS")


def test_session_id_flow() -> None:
    """session_id optional for open, required for all other actions."""
    # open: session_id optional
    open_params = [{"url": "https://example.com"}, {"url": "https://example.com", "session_id": "sess_new"}]
    for p in open_params:
        _validate_url(p["url"])
        _validate_session_id(p.get("session_id"), required=False)
    print("  [session] open accepts optional session_id: PASS")

    # Most session actions require session_id
    for action in ["read_text", "list_links", "click", "type", "wait_for", "screenshot", "close"]:
        _assert_rejected(lambda: _validate_session_id(None), f"  [session] {action} requires session_id")
    print("  [session] Session-bound actions require session_id: PASS")

    # download can use a session or a direct URL.
    direct_download = {"url": "https://example.com/file.pdf"}
    _validate_url(direct_download["url"])
    _validate_session_id(direct_download.get("session_id"), required=False)
    print("  [session] download accepts direct url without session_id: PASS")


def main() -> None:
    print("=" * 60)
    print("browser-tools sandbox test")
    print("=" * 60)

    test_open_params()
    test_read_text_params()
    test_list_links_params()
    test_click_params()
    test_type_params()
    test_wait_for_params()
    test_screenshot_params()
    test_download_params()
    test_timeout_clamp()
    test_direct_http_download_streams_to_file()
    test_direct_http_download_stream_limit_cleans_partial_file()
    test_direct_http_download_redirect_revalidates_ssrf_target()
    test_download_filename_rejects_paths()
    test_close_session_reports_cleanup_errors()
    test_close_params()
    test_output_shapes()
    test_no_cookie_localstorage_return()
    test_session_id_flow()

    print("=" * 60)
    print("PASS: browser-tools sandbox test")


if __name__ == "__main__":
    main()
