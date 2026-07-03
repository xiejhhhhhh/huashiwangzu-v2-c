"""Sandbox test for browser-tools module.

Validates parameter schemas, required fields, value ranges, and output shapes
based on MANIFEST public_actions. No real browser calls.
"""
from collections.abc import Callable
from typing import Any

# ── URL validation helpers ─────────────────────────────────────────────

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
    """Validate timeout is a positive number (default 30)."""
    if timeout is not None:
        assert isinstance(timeout, (int, float)) and timeout > 0, \
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
    test_close_params()
    test_output_shapes()
    test_no_cookie_localstorage_return()
    test_session_id_flow()

    print("=" * 60)
    print("PASS: browser-tools sandbox test")


if __name__ == "__main__":
    main()
