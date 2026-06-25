import pytest

from app.gateway.router import _call_with_retry
from app.gateway.error_classifier import (
    classify_error,
    compute_delay,
    max_attempts_for_category,
    ErrorClassification,
)


class SuccessOnNthProvider:
    def __init__(self, succeed_on: int = 2) -> None:
        self.calls = 0
        self.succeed_on = succeed_on

    async def chat(self, messages, model, temperature=0.7, max_tokens=4096, tools=None, timeout=None):
        self.calls += 1
        if self.calls < self.succeed_on:
            exc = RuntimeError("temporary upstream failure")
            setattr(exc, "status_code", 502)
            raise exc
        return {"ok": True}


class StatusCodeProvider:
    def __init__(self, status: int) -> None:
        self.status = status

    async def chat(self, messages, model, temperature=0.7, max_tokens=4096, tools=None, timeout=None):
        exc = RuntimeError(f"error {self.status}")
        setattr(exc, "status_code", self.status)
        raise exc


class TimeoutProvider:
    async def chat(self, messages, model, temperature=0.7, max_tokens=4096, tools=None, timeout=None):
        raise TimeoutError("request timed out")


class ConnectionErrorProvider:
    async def chat(self, messages, model, temperature=0.7, max_tokens=4096, tools=None, timeout=None):
        raise ConnectionError("upstream unreachable")


@pytest.mark.asyncio
async def test_retryable_server_error_is_retried() -> None:
    provider = SuccessOnNthProvider(succeed_on=2)
    result = await _call_with_retry(provider, messages=[], model="demo", temperature=0.7, max_tokens=1, tools=None)
    assert result == {"ok": True}
    assert provider.calls == 2


@pytest.mark.asyncio
async def test_auth_error_not_retried() -> None:
    provider = StatusCodeProvider(401)
    with pytest.raises(RuntimeError, match="error 401"):
        await _call_with_retry(provider, messages=[], model="demo", temperature=0.7, max_tokens=1, tools=None)


@pytest.mark.asyncio
async def test_forbidden_not_retried() -> None:
    provider = StatusCodeProvider(403)
    with pytest.raises(RuntimeError, match="error 403"):
        await _call_with_retry(provider, messages=[], model="demo", temperature=0.7, max_tokens=1, tools=None)


@pytest.mark.asyncio
async def test_timeout_error_is_retried() -> None:
    provider = TimeoutProvider()
    with pytest.raises(TimeoutError):
        await _call_with_retry(provider, messages=[], model="demo", temperature=0.7, max_tokens=1, tools=None)


@pytest.mark.asyncio
async def test_connection_error_is_retried() -> None:
    provider = ConnectionErrorProvider()
    with pytest.raises(ConnectionError):
        await _call_with_retry(provider, messages=[], model="demo", temperature=0.7, max_tokens=1, tools=None)


# ── Classifier unit tests ──


def test_classify_429_rate_limit() -> None:
    clf = classify_error(status_code=429, body='{"error": "rate limited", "retry_after": 5}')
    assert clf.category == "rate_limit"
    assert clf.retryable is True
    assert clf.retry_after == 5.0


def test_classify_429_no_body() -> None:
    clf = classify_error(status_code=429)
    assert clf.category == "rate_limit"
    assert clf.retryable is True
    assert clf.retry_after is None


def test_classify_401_auth() -> None:
    clf = classify_error(status_code=401)
    assert clf.category == "auth"
    assert clf.retryable is False


def test_classify_403_auth() -> None:
    clf = classify_error(status_code=403)
    assert clf.category == "auth"
    assert clf.retryable is False


def test_classify_500_server() -> None:
    clf = classify_error(status_code=500)
    assert clf.category == "server"
    assert clf.retryable is True


def test_classify_502_server() -> None:
    clf = classify_error(status_code=502)
    assert clf.category == "server"
    assert clf.retryable is True


def test_classify_timeout_exception() -> None:
    clf = classify_error(exception=TimeoutError("timed out"))
    assert clf.category == "timeout"
    assert clf.retryable is True


def test_classify_unknown() -> None:
    clf = classify_error(status_code=418)
    assert clf.category == "unknown"
    assert clf.retryable is True


def test_classify_quota_body() -> None:
    clf = classify_error(status_code=400, body='{"error": "insufficient_quota"}')
    assert clf.category == "quota"
    assert clf.retryable is False


def test_compute_delay_uses_retry_after() -> None:
    clf = ErrorClassification("rate_limit", True, retry_after=5.0)
    delay = compute_delay(clf, attempt=0)
    assert 4.0 <= delay <= 6.0


def test_compute_delay_exponential_backoff() -> None:
    clf = ErrorClassification("server", True)
    d0 = compute_delay(clf, attempt=0)
    d1 = compute_delay(clf, attempt=1)
    d2 = compute_delay(clf, attempt=2)
    assert 0.5 <= d0 <= 1.5
    assert d1 > d0
    assert d2 > d1


def test_max_attempts_non_retryable() -> None:
    assert max_attempts_for_category("auth") == 1
    assert max_attempts_for_category("quota") == 1


def test_max_attempts_retryable() -> None:
    assert max_attempts_for_category("server", 3) == 3
    assert max_attempts_for_category("timeout", 3) == 3


def test_max_attempts_unknown() -> None:
    assert max_attempts_for_category("unknown", 3) == 2


# ── httpx.Timeout constructor regression tests ──

import httpx

def test_resolve_timeout_all_fields_default() -> None:
    from app.gateway.openai_provider import OpenAIProvider
    provider = OpenAIProvider(api_url="http://test", api_key="test")
    t, chunk = provider._resolve_timeout(None)
    assert isinstance(t, httpx.Timeout)
    assert t.connect == 10
    assert t.read == 120
    assert t.write == 30
    # pool 必须是具体值(取 connect 兜底): pool=None 会让 httpx.Timeout 在运行期拒绝, 致网关全崩
    assert t.pool == 10
    assert chunk == 60

def test_resolve_timeout_without_write_fallback() -> None:
    from app.gateway.openai_provider import OpenAIProvider
    provider = OpenAIProvider(api_url="http://test", api_key="test")
    t, chunk = provider._resolve_timeout({"connect": 5, "read": 60, "stream_chunk": 30})
    assert isinstance(t, httpx.Timeout)
    assert t.connect == 5
    assert t.read == 60
    assert t.write == 30
    assert chunk == 30

def test_resolve_timeout_all_custom() -> None:
    from app.gateway.openai_provider import OpenAIProvider
    provider = OpenAIProvider(api_url="http://test", api_key="test")
    t, chunk = provider._resolve_timeout({"connect": 3, "read": 15, "write": 5, "stream_chunk": 10})
    assert isinstance(t, httpx.Timeout)
    assert t.connect == 3
    assert t.read == 15
    assert t.write == 5
    assert chunk == 10
