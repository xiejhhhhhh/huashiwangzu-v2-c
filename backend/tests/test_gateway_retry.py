import pytest
from app.gateway.contract import ModelRequest, ModelResponse
from app.gateway.router import _call_with_unified_retry


class RetryableProvider:
    def __init__(self) -> None:
        self.calls = 0

    async def chat(self, messages, model, temperature=0.7, max_tokens=4096, tools=None):
        self.calls += 1
        if self.calls < 2:
            exc = RuntimeError("temporary upstream failure")
            exc.status_code = 502
            raise exc
        return {"choices": [{"message": {"content": "ok"}, "finish_reason": "stop"}]}


class NonRetryableProvider:
    async def chat(self, messages, model, temperature=0.7, max_tokens=4096, tools=None):
        exc = RuntimeError("invalid api key")
        exc.status_code = 401
        raise exc


@pytest.mark.asyncio
async def test_retryable_provider_is_retried_once() -> None:
    provider = RetryableProvider()
    result = await _call_with_unified_retry(
        provider=provider,
        req=ModelRequest(messages=[], temperature=0.7, max_tokens=1),
        model="demo",
        caller_module="test",
        profile_key="demo",
        provider_name="test",
    )
    assert isinstance(result, ModelResponse)
    assert result.content == "ok"
    assert provider.calls == 2


@pytest.mark.asyncio
async def test_non_retryable_provider_returns_error_response() -> None:
    provider = NonRetryableProvider()
    result = await _call_with_unified_retry(
        provider=provider,
        req=ModelRequest(messages=[], temperature=0.7, max_tokens=1),
        model="demo",
        caller_module="test",
        profile_key="demo",
        provider_name="test",
    )
    assert isinstance(result, ModelResponse)
    assert result.error is not None
    assert "invalid api key" in result.error
