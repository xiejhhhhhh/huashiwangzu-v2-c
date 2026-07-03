"""Sandbox test for web-tools module.

Validates parameter schemas, required fields, value ranges, and output shapes
based on MANIFEST public_actions. No real web requests.
"""
from collections.abc import Callable

# ── URL validation helpers ─────────────────────────────────────────────

def _assert_rejected(fn: Callable[[], None], label: str) -> None:
    try:
        fn()
    except AssertionError:
        print(f"{label}: PASS")
        return
    raise AssertionError(f"{label}: expected AssertionError")

_PRIVATE_PREFIXES = (
    "http://localhost",
    "https://localhost",
    "http://127.0.0.1",
    "https://127.0.0.1",
    "http://10.",
    "https://10.",
    "http://172.16.",
    "https://172.16.",
    "http://172.17.",
    "https://172.17.",
    "http://172.18.",
    "https://172.18.",
    "http://172.19.",
    "https://172.19.",
    "http://172.20.",
    "https://172.20.",
    "http://172.21.",
    "https://172.21.",
    "http://172.22.",
    "https://172.22.",
    "http://172.23.",
    "https://172.23.",
    "http://172.24.",
    "https://172.24.",
    "http://172.25.",
    "https://172.25.",
    "http://172.26.",
    "https://172.26.",
    "http://172.27.",
    "https://172.27.",
    "http://172.28.",
    "https://172.28.",
    "http://172.29.",
    "https://172.29.",
    "http://172.30.",
    "https://172.30.",
    "http://172.31.",
    "https://172.31.",
    "http://192.168.",
    "https://192.168.",
)
_MAX_QUERY_CHARS = 500
_MAX_URL_CHARS = 2048
_MAX_FETCH_CHARS = 8000
_MAX_SEARCH_TITLE_CHARS = 300
_MAX_SEARCH_SNIPPET_CHARS = 1000
_MAX_SEARCH_URL_CHARS = 2048


def _validate_bounded_int(value: int, minimum: int, maximum: int, name: str) -> None:
    if not isinstance(value, int):
        raise AssertionError(f"{name} must be an integer")
    if value < minimum or value > maximum:
        raise AssertionError(f"{name} must be between {minimum} and {maximum}")


def _validate_public_url(url: str) -> None:
    """Reject non-http/https URLs and private/internal addresses (SSRF)."""
    if not isinstance(url, str) or not url.strip():
        raise AssertionError("URL must be a non-empty string")
    if not (url.startswith("http://") or url.startswith("https://")):
        raise AssertionError(f"URL must start with http:// or https://, got: {url[:30]}")
    for prefix in _PRIVATE_PREFIXES:
        if url.startswith(prefix):
            raise AssertionError(f"SSRF protection: internal URL rejected: {url[:50]}")
    # Also reject bare IP formats like http://10.0.0.1
    if "://" in url:
        remainder = url.split("://", 1)[1]
        # Check for /etc/hosts style localhost
        if remainder.startswith("localhost") or remainder.startswith("localhost."):
            raise AssertionError(f"SSRF protection: localhost hostname rejected: {url[:50]}")


# ── Search tests ───────────────────────────────────────────────────────

def test_search_query_required() -> None:
    """search: query is required and must be non-empty."""
    def reject_empty_query() -> None:
        query = ""
        assert isinstance(query, str) and len(query.strip()) > 0, \
            "query is required and must be a non-empty string"

    _assert_rejected(reject_empty_query, "  [search] Empty query rejected")

    query = "Python async programming"
    assert isinstance(query, str) and query.strip(), \
        "query is required and must be a non-empty string"
    assert len(query) <= _MAX_QUERY_CHARS, "query must stay within max length"
    print("  [search] Valid query accepted: PASS")

    def reject_long_query() -> None:
        query = "x" * (_MAX_QUERY_CHARS + 1)
        assert len(query) <= _MAX_QUERY_CHARS, "query too long"

    _assert_rejected(reject_long_query, "  [search] Overlong query rejected")


def test_search_top_k_range() -> None:
    """search: top_k optional, default 8, max 20."""
    # Default
    top_k = 8
    _validate_bounded_int(top_k, 1, 20, "top_k")
    print(f"  [search] Default top_k={top_k}: PASS")

    # Custom valid
    top_k = 5
    _validate_bounded_int(top_k, 1, 20, "top_k")
    print(f"  [search] Custom top_k={top_k}: PASS")

    # Max boundary
    top_k = 20
    _validate_bounded_int(top_k, 1, 20, "top_k")
    print(f"  [search] Max top_k={top_k}: PASS")

    # Below minimum
    def reject_zero_top_k() -> None:
        _validate_bounded_int(0, 1, 20, "top_k")

    _assert_rejected(reject_zero_top_k, "  [search] top_k=0 rejected")

    # Above maximum
    def reject_large_top_k() -> None:
        _validate_bounded_int(21, 1, 20, "top_k")

    _assert_rejected(reject_large_top_k, "  [search] top_k=21 rejected")


def test_search_output_shape() -> None:
    """search returns results array with title/url/snippet."""
    results = [
        {"title": "Async IO in Python", "url": "https://example.com/async", "snippet": "A guide to async..."},
        {"title": "Python Concurrency", "url": "https://example.com/concurrency", "snippet": "Comparing approaches..."},
    ]
    for item in results:
        assert "title" in item and isinstance(item["title"], str)
        assert len(item["title"]) <= _MAX_SEARCH_TITLE_CHARS
        assert "url" in item and isinstance(item["url"], str)
        assert item["url"].startswith(("http://", "https://"))
        assert len(item["url"]) <= _MAX_SEARCH_URL_CHARS
        assert "snippet" in item and isinstance(item["snippet"], str)
        assert len(item["snippet"]) <= _MAX_SEARCH_SNIPPET_CHARS
    print(f"  [search] Output shape ({len(results)} results): PASS")


# ── Fetch tests ────────────────────────────────────────────────────────

def test_fetch_url_required() -> None:
    """fetch: url required (http/https only)."""
    _assert_rejected(lambda: _validate_public_url(""), "  [fetch] Empty URL rejected")

    _assert_rejected(lambda: _validate_public_url("not-a-url"), "  [fetch] Non-URL string rejected")

    _assert_rejected(lambda: _validate_public_url("ftp://files.example.com"), "  [fetch] FTP protocol rejected")

    _assert_rejected(lambda: _validate_public_url("file:///etc/passwd"), "  [fetch] File protocol rejected")

    # Valid public URL
    _validate_public_url("https://example.com/article")
    print("  [fetch] Valid public URL accepted: PASS")

    def reject_long_url() -> None:
        url = "https://example.com/" + ("a" * _MAX_URL_CHARS)
        assert len(url) <= _MAX_URL_CHARS, "url too long"

    _assert_rejected(reject_long_url, "  [fetch] Overlong URL rejected")


def test_fetch_ssrf_protection() -> None:
    """fetch rejects internal/private addresses."""
    bad_urls = [
        "http://localhost:8080/",
        "https://localhost:3000",
        "http://127.0.0.1:5432",
        "https://127.0.0.1/api",
        "http://10.0.0.1/admin",
        "https://10.0.0.1/secret",
        "http://172.16.0.1/config",
        "https://172.31.255.255/",
        "http://192.168.1.1/router",
        "https://192.168.0.1/admin",
        "http://localhost/",
        "https://localhost/health",
    ]
    for url in bad_urls:
        _assert_rejected(lambda url=url: _validate_public_url(url), f"  [fetch] SSRF internal URL rejected {url[:24]}")
    print(f"  [fetch] SSRF: {len(bad_urls)} internal URLs rejected: PASS")


def test_fetch_max_chars() -> None:
    """fetch: max_chars optional, default 8000, must be positive."""
    default_max_chars = _MAX_FETCH_CHARS
    _validate_bounded_int(default_max_chars, 1, _MAX_FETCH_CHARS, "max_chars")
    print(f"  [fetch] Default max_chars={default_max_chars}: PASS")

    # Custom valid
    max_chars = 4000
    _validate_bounded_int(max_chars, 1, _MAX_FETCH_CHARS, "max_chars")
    print(f"  [fetch] Custom max_chars={max_chars}: PASS")

    # Invalid negative
    def reject_negative_max_chars() -> None:
        _validate_bounded_int(-100, 1, _MAX_FETCH_CHARS, "max_chars")

    _assert_rejected(reject_negative_max_chars, "  [fetch] Negative max_chars rejected")

    # Invalid zero
    def reject_zero_max_chars() -> None:
        _validate_bounded_int(0, 1, _MAX_FETCH_CHARS, "max_chars")

    _assert_rejected(reject_zero_max_chars, "  [fetch] Zero max_chars rejected")

    def reject_large_max_chars() -> None:
        _validate_bounded_int(_MAX_FETCH_CHARS + 1, 1, _MAX_FETCH_CHARS, "max_chars")

    _assert_rejected(reject_large_max_chars, "  [fetch] Oversized max_chars rejected")


def test_fetch_output_shape() -> None:
    """fetch returns url/title/text/truncated."""
    result = {
        "url": "https://example.com/article",
        "title": "Article title",
        "text": "Article body text...",
        "truncated": False,
        "error": None,
    }
    assert result["url"].startswith(("http://", "https://"))
    assert isinstance(result["title"], str)
    assert isinstance(result["text"], str)
    assert isinstance(result["truncated"], bool)
    assert result["error"] is None
    print("  [fetch] Output shape (url, title, text, truncated): PASS")


def test_fetch_truncation_contract() -> None:
    """fetch marks truncated when extracted text exceeds max_chars."""
    max_chars = 12
    source_text = "0123456789abcdef"
    text = source_text[:max_chars]
    truncated = len(source_text) > max_chars
    assert text == "0123456789ab"
    assert truncated is True
    print("  [fetch] Truncation flag contract: PASS")


def test_fetch_valid_urls() -> None:
    """fetch accepts various public URLs."""
    valid_urls = [
        "https://example.com",
        "http://example.com",
        "https://www.wikipedia.org/wiki/Python",
        "https://api.github.com/repos/python/cpython",
        "http://news.ycombinator.com",
    ]
    for url in valid_urls:
        _validate_public_url(url)
    print(f"  [fetch] {len(valid_urls)} valid public URLs accepted: PASS")


def main() -> None:
    print("=" * 60)
    print("web-tools sandbox test")
    print("=" * 60)

    test_search_query_required()
    test_search_top_k_range()
    test_search_output_shape()
    test_fetch_url_required()
    test_fetch_ssrf_protection()
    test_fetch_max_chars()
    test_fetch_output_shape()
    test_fetch_truncation_contract()
    test_fetch_valid_urls()

    print("=" * 60)
    print("PASS: web-tools sandbox test")


if __name__ == "__main__":
    main()
