import pytest

from app.gateway.router import _call_with_retry


class RetryableProvider:
    def __init__(self) -> None:
        self.calls = 0

    async def chat(self, messages, model, temperature=0.7, max_tokens=4096, tools=None):
        self.calls += 1
        if self.calls < 2:
            exc = RuntimeError("temporary upstream failure")
            setattr(exc, "status_code", 502)
            raise exc
        return {"ok": True}


class NonRetryableProvider:
    async def chat(self, messages, model, temperature=0.7, max_tokens=4096, tools=None):
        exc = RuntimeError("invalid api key")
        setattr(exc, "status_code", 401)
        raise exc


@pytest.mark.asyncio
async def test_retryable_provider_is_retried_once() -> None:
    provider = RetryableProvider()
    result = await _call_with_retry(provider, messages=[], model="demo", temperature=0.7, max_tokens=1, tools=None)
    assert result == {"ok": True}
    assert provider.calls == 2


@pytest.mark.asyncio
async def test_non_retryable_provider_bubbles_error() -> None:
    provider = NonRetryableProvider()
    with pytest.raises(RuntimeError, match="invalid api key"):
        await _call_with_retry(provider, messages=[], model="demo", temperature=0.7, max_tokens=1, tools=None)
