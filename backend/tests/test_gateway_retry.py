from io import BytesIO

import httpx
import pytest
from app.gateway import openai_provider as openai_provider_module
from app.gateway import router as gateway_router_module
from app.gateway.config import get_model_type_config, get_models_config
from app.gateway.contract import ModelRequest, ModelResponse
from app.gateway.error_classifier import ErrorClassification
from app.gateway.local import LocalProvider
from app.gateway.openai_provider import OpenAIProvider, _payload_preview
from app.gateway.router import (
    ModelGatewayRouter,
    RetryBudget,
    _call_with_unified_retry,
    _format_exception_detail,
    _prepare_vision_image_for_model,
    _retry_budget_from_profile,
    _retry_delay,
)
from app.services.model_watchdog import launcher as watchdog_launcher
from app.services.model_watchdog.registry import ModelRecord


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


class ProtocolErrorProvider:
    def __init__(self) -> None:
        self.calls = 0

    async def chat(self, messages, model, temperature=0.7, max_tokens=4096, tools=None):
        self.calls += 1
        exc = RuntimeError("invalid_request_error: tool_calls must be followed by tool messages")
        exc.status_code = 400
        raise exc


class AlwaysFailProvider:
    def __init__(self, message: str = "rate limit", status_code: int = 429) -> None:
        self.calls = 0
        self.message = message
        self.status_code = status_code

    async def chat(self, messages, model, temperature=0.7, max_tokens=4096, tools=None):
        self.calls += 1
        exc = RuntimeError(self.message)
        exc.status_code = self.status_code
        raise exc


class LocalSuccessProvider:
    def __init__(self, content: str = "local ok") -> None:
        self.calls = 0
        self.content = content

    async def chat(self, messages, model, temperature=0.7, max_tokens=4096, tools=None):
        self.calls += 1
        return {"content": self.content, "thinking": "", "finish_reason": "stop"}


class OpenAICompatSuccessProvider:
    def __init__(self, content: str = "ok", provider_shape: str = "openai") -> None:
        self.calls = 0
        self.content = content
        self.provider_shape = provider_shape

    async def chat(self, messages, model, temperature=0.7, max_tokens=4096, tools=None):
        self.calls += 1
        if self.provider_shape == "ollama":
            return {"message": {"role": "assistant", "content": self.content}, "done": True}
        return {"choices": [{"message": {"content": self.content}, "finish_reason": "stop"}]}


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


@pytest.mark.asyncio
async def test_protocol_error_is_not_retried() -> None:
    provider = ProtocolErrorProvider()
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
    assert "tool_calls must be followed" in result.error
    assert provider.calls == 1


def test_profile_retry_budget_respects_zero_delay() -> None:
    budget = _retry_budget_from_profile({"retry_delay_seconds": 0}, None)

    assert budget is not None
    assert budget.base_delay_seconds == 0
    assert _retry_delay(ErrorClassification("server", True), 0, budget) == 0.1


def test_invalid_api_key_body_is_classified_as_auth_before_protocol() -> None:
    classification = gateway_router_module.classify_error(
        status_code=401,
        body='{"error":{"code":"invalid_api_key","message":"missing or invalid API key","type":"invalid_request_error"}}',
    )

    assert classification.category == "auth"
    assert classification.retryable is False


def test_format_exception_detail_keeps_blank_exception_actionable() -> None:
    assert _format_exception_detail(TimeoutError()) == "TimeoutError"


def test_prepare_vision_image_resizes_large_images_before_multimodal_send() -> None:
    image_mod = pytest.importorskip("PIL.Image")
    image = image_mod.new("RGB", (4200, 2600), "white")
    buf = BytesIO()
    image.save(buf, format="PNG")

    prepared, mime_type, metadata = _prepare_vision_image_for_model(
        buf.getvalue(),
        "image/png",
    )

    assert mime_type == "image/jpeg"
    assert len(prepared) <= 1800 * 1024
    assert metadata["resized"] is True
    assert metadata["reencoded"] is True
    assert max(metadata["prepared_size"]) == 1600
    assert metadata["jpeg_quality_start"] == 84
    assert metadata["jpeg_quality_floor"] == 72
    assert metadata["vlm_ready"] is True
    assert metadata["prepared_md5"]


@pytest.mark.asyncio
async def test_chat_rejects_image_payloads_before_provider_call() -> None:
    router = ModelGatewayRouter.__new__(ModelGatewayRouter)
    router._providers = {}

    result = await router.chat(
        messages=[
            {
                "role": "user",
                "content": [
                    {"type": "image_url", "image_url": {"url": "data:image/png;base64,abc"}},
                    {"type": "text", "text": "describe this"},
                ],
            }
        ],
    )

    assert result["error"]
    assert result["diagnostics"]["policy"] == "vision_images_must_use_describe_image"


def test_openai_provider_session_affinity_header_is_payload_scoped() -> None:
    provider = OpenAIProvider(
        api_url="http://127.0.0.1:61462/v1/chat/completions",
        api_key="test-key",
        provider_name="gptstore-text",
        session_affinity={"header": "X-Session-ID", "prefix": "knowledge-gptstore"},
    )
    payload_a = provider._build_payload(
        [{"role": "user", "content": "doc 1 page 1"}],
        "gpt-5.5",
        0.2,
        128,
        False,
        None,
    )
    payload_b = provider._build_payload(
        [{"role": "user", "content": "doc 1 page 2"}],
        "gpt-5.5",
        0.2,
        128,
        False,
        None,
    )

    headers_a1 = provider._headers(payload_a, "gpt-5.5")
    headers_a2 = provider._headers(payload_a, "gpt-5.5")
    headers_b = provider._headers(payload_b, "gpt-5.5")

    assert headers_a1["Authorization"] == "Bearer test-key"
    assert headers_a1["X-Session-ID"].startswith("knowledge-gptstore:")
    assert headers_a1["X-Session-ID"] == headers_a2["X-Session-ID"]
    assert headers_a1["X-Session-ID"] != headers_b["X-Session-ID"]


def test_openai_provider_session_affinity_can_be_request_scoped() -> None:
    provider = OpenAIProvider(
        api_url="http://127.0.0.1:61462/v1/chat/completions",
        api_key="test-key",
        provider_name="gptstore-text",
        session_affinity={
            "header": "X-Session-ID",
            "prefix": "knowledge-gptstore",
            "scope": "request",
        },
    )
    payload = provider._build_payload(
        [{"role": "user", "content": "same payload"}],
        "gpt-5.5",
        0.2,
        128,
        False,
        None,
    )

    headers_a = provider._headers(payload, "gpt-5.5")
    headers_b = provider._headers(payload, "gpt-5.5")

    assert headers_a["X-Session-ID"].startswith("knowledge-gptstore:")
    assert headers_b["X-Session-ID"].startswith("knowledge-gptstore:")
    assert headers_a["X-Session-ID"] != headers_b["X-Session-ID"]


def test_openai_provider_payload_preview_redacts_image_data_urls() -> None:
    preview = _payload_preview({
        "messages": [
            {
                "role": "user",
                "content": [
                    {
                        "type": "image_url",
                        "image_url": {"url": "data:image/png;base64,VERY_LONG_IMAGE_BYTES"},
                    },
                    {"type": "text", "text": "保留业务文本用于定位错误"},
                ],
            }
        ]
    })

    assert "VERY_LONG_IMAGE_BYTES" not in preview
    assert "<image data url redacted>" in preview
    assert "保留业务文本用于定位错误" in preview


@pytest.mark.asyncio
async def test_openai_provider_auth_recovery_rotates_session_on_configured_401(monkeypatch) -> None:
    seen_sessions: list[str] = []

    class FakeAsyncClient:
        def __init__(self, **kwargs) -> None:
            self.kwargs = kwargs

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb) -> None:
            return None

        async def post(self, url, json, headers):
            seen_sessions.append(headers["X-Session-ID"])
            request = httpx.Request("POST", url)
            if len(seen_sessions) == 1:
                return httpx.Response(
                    401,
                    json={"error": {"message": "bad relay account"}},
                    request=request,
                )
            return httpx.Response(
                200,
                json={"choices": [{"message": {"content": "ok"}, "finish_reason": "stop"}]},
                request=request,
            )

    monkeypatch.setattr(openai_provider_module.httpx, "AsyncClient", FakeAsyncClient)
    provider = OpenAIProvider(
        api_url="http://127.0.0.1:61462/v1/chat/completions",
        api_key="test-key",
        provider_name="gptstore-text",
        session_affinity={
            "header": "X-Session-ID",
            "prefix": "knowledge-gptstore",
            "scope": "request",
        },
        auth_recovery={
            "strategy": "rotate_session",
            "status_codes": [401],
            "max_attempts": 2,
            "delay_seconds": 0,
        },
    )

    result = await provider.chat(
        messages=[{"role": "user", "content": "hello"}],
        model="gpt-5.5",
        temperature=0.2,
        max_tokens=128,
    )

    assert result["choices"][0]["message"]["content"] == "ok"
    assert len(seen_sessions) == 2
    assert seen_sessions[0].startswith("knowledge-gptstore:")
    assert seen_sessions[1].startswith("knowledge-gptstore:")
    assert seen_sessions[0] != seen_sessions[1]


@pytest.mark.asyncio
async def test_openai_provider_auth_recovery_exhaustion_raises_final_401(monkeypatch) -> None:
    seen_sessions: list[str] = []

    class FakeAsyncClient:
        def __init__(self, **kwargs) -> None:
            self.kwargs = kwargs

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb) -> None:
            return None

        async def post(self, url, json, headers):
            seen_sessions.append(headers["X-Session-ID"])
            return httpx.Response(
                401,
                json={"error": {"message": "all relay accounts failed"}},
                request=httpx.Request("POST", url),
            )

    monkeypatch.setattr(openai_provider_module.httpx, "AsyncClient", FakeAsyncClient)
    provider = OpenAIProvider(
        api_url="http://127.0.0.1:61462/v1/chat/completions",
        api_key="test-key",
        provider_name="gptstore-text",
        session_affinity={
            "header": "X-Session-ID",
            "prefix": "knowledge-gptstore",
            "scope": "request",
        },
        auth_recovery={
            "strategy": "rotate_session",
            "status_codes": [401],
            "max_attempts": 2,
            "delay_seconds": 0,
        },
    )

    with pytest.raises(httpx.HTTPStatusError):
        await provider.chat(
            messages=[{"role": "user", "content": "hello"}],
            model="gpt-5.5",
            temperature=0.2,
            max_tokens=128,
        )

    assert len(seen_sessions) == 2
    assert seen_sessions[0] != seen_sessions[1]


@pytest.mark.asyncio
async def test_openai_provider_auth_recovery_is_opt_in(monkeypatch) -> None:
    calls = 0

    class FakeAsyncClient:
        def __init__(self, **kwargs) -> None:
            self.kwargs = kwargs

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb) -> None:
            return None

        async def post(self, url, json, headers):
            nonlocal calls
            calls += 1
            return httpx.Response(
                401,
                json={"error": {"message": "invalid api key"}},
                request=httpx.Request("POST", url),
            )

    monkeypatch.setattr(openai_provider_module.httpx, "AsyncClient", FakeAsyncClient)
    provider = OpenAIProvider(
        api_url="http://127.0.0.1:61462/v1/chat/completions",
        api_key="test-key",
        provider_name="gptstore-text",
        session_affinity={
            "header": "X-Session-ID",
            "prefix": "knowledge-gptstore",
            "scope": "request",
        },
    )

    with pytest.raises(httpx.HTTPStatusError):
        await provider.chat(
            messages=[{"role": "user", "content": "hello"}],
            model="gpt-5.5",
            temperature=0.2,
            max_tokens=128,
        )

    assert calls == 1


@pytest.mark.asyncio
async def test_profile_retry_budget_uses_fixed_delay(monkeypatch) -> None:
    profiles = {
        "gpt-5.5-knowledge": {
            "provider": "gptstore-text",
            "model": "gpt-5.5",
            "temperature": 0.2,
            "max_tokens": 128,
            "retry_max_attempts": 3,
            "retry_delay_seconds": 30,
            "retry_strategy": "fixed",
        },
        "deepseek-v4-flash": {
            "provider": "opencode",
            "model": "deepseek-v4-flash",
            "temperature": 0.7,
            "max_tokens": 128,
        },
    }
    gpt55 = AlwaysFailProvider("bad gateway", status_code=502)
    deepseek = OpenAICompatSuccessProvider("deepseek fallback ok")
    waits: list[float] = []

    def capture_sleep(seconds: float):
        waits.append(seconds)

        async def _noop() -> None:
            return None

        return _noop()

    monkeypatch.setattr(gateway_router_module, "MODEL_PROFILES", profiles)
    monkeypatch.setattr(gateway_router_module.asyncio, "sleep", capture_sleep)
    monkeypatch.setattr(
        gateway_router_module,
        "get_model_type_config",
        lambda model_type: {
            "primary": "gpt-5.5-knowledge",
            "fallback_on_explicit_profile": True,
            "fallback_chain": ["deepseek-v4-flash"],
            "profiles": profiles,
        } if model_type == "llm" else {},
    )

    router = ModelGatewayRouter.__new__(ModelGatewayRouter)
    router._providers = {"gptstore-text": gpt55, "opencode": deepseek}

    result = await router.chat(
        messages=[{"role": "user", "content": "hello"}],
        profile_key="gpt-5.5-knowledge",
    )

    assert result["content"] == "deepseek fallback ok"
    assert gpt55.calls == 3
    assert deepseek.calls == 1
    assert waits == [30, 30]
    assert result["diagnostics"]["fallback_used"] is True
    assert result["diagnostics"]["selected_profile"] == "deepseek-v4-flash"


@pytest.mark.asyncio
async def test_chat_falls_back_from_explicit_cloud_profile(monkeypatch) -> None:
    profiles = {
        "cloud-primary": {
            "provider": "cloud",
            "model": "cloud-primary",
            "temperature": 0.7,
            "max_tokens": 128,
        },
        "local-fallback": {
            "provider": "local",
            "model": "local-fallback",
            "temperature": 0.2,
            "max_tokens": 64,
        },
    }
    cloud = AlwaysFailProvider("quota exhausted")
    local = LocalSuccessProvider("local fallback ok")

    monkeypatch.setattr(gateway_router_module, "MODEL_PROFILES", profiles)
    monkeypatch.setattr(
        gateway_router_module,
        "get_model_type_config",
        lambda model_type: {
            "primary": "cloud-primary",
            "fallback_on_explicit_profile": True,
            "fallback_chain": ["local-fallback"],
            "profiles": profiles,
        } if model_type == "llm" else {},
    )

    router = ModelGatewayRouter.__new__(ModelGatewayRouter)
    router._providers = {"cloud": cloud, "local": local}

    result = await router.chat(
        messages=[{"role": "user", "content": "hello"}],
        profile_key="cloud-primary",
        budget=RetryBudget(max_attempts=1),
    )

    assert result["content"] == "local fallback ok"
    assert "error" not in result
    assert cloud.calls == 1
    assert local.calls == 1
    assert result["diagnostics"]["fallback_used"] is True
    assert result["diagnostics"]["selected_profile"] == "local-fallback"


@pytest.mark.asyncio
async def test_profile_fallback_chain_overrides_global_chain(monkeypatch) -> None:
    profiles = {
        "gpt-5.5-knowledge": {
            "provider": "gptstore-text",
            "model": "gpt-5.5",
            "temperature": 0.2,
            "max_tokens": 128,
            "fallback_policy": "knowledge-text",
        },
        "gemma-4": {
            "provider": "llama",
            "model": "gemma-4",
            "temperature": 0.2,
            "max_tokens": 64,
        },
        "deepseek-v4-flash": {
            "provider": "opencode",
            "model": "deepseek-v4-flash",
            "temperature": 0.2,
            "max_tokens": 64,
        },
    }
    gpt55 = AlwaysFailProvider("relay timeout", status_code=504)
    gemma = OpenAICompatSuccessProvider("should not be used")
    deepseek = OpenAICompatSuccessProvider("direct fallback ok")

    monkeypatch.setattr(gateway_router_module, "MODEL_PROFILES", profiles)
    monkeypatch.setattr(
        gateway_router_module,
        "get_models_config",
        lambda: {"fallback_policies": {"knowledge-text": {"chain": ["deepseek-v4-flash"]}}},
    )
    monkeypatch.setattr(
        gateway_router_module,
        "get_model_type_config",
        lambda model_type: {
            "primary": "gpt-5.5-knowledge",
            "fallback_on_explicit_profile": True,
            "fallback_chain": ["gemma-4"],
            "profiles": profiles,
        } if model_type == "llm" else {},
    )

    router = ModelGatewayRouter.__new__(ModelGatewayRouter)
    router._providers = {"gptstore-text": gpt55, "llama": gemma, "opencode": deepseek}

    result = await router.chat(
        messages=[{"role": "user", "content": "hello"}],
        profile_key="gpt-5.5-knowledge",
        budget=RetryBudget(max_attempts=1),
    )

    assert result["content"] == "direct fallback ok"
    assert gpt55.calls == 1
    assert gemma.calls == 0
    assert deepseek.calls == 1
    assert result["diagnostics"]["candidates"] == ["gpt-5.5-knowledge", "deepseek-v4-flash"]
    assert result["diagnostics"]["selected_profile"] == "deepseek-v4-flash"


@pytest.mark.asyncio
async def test_profile_inline_fallback_chain_remains_supported(monkeypatch) -> None:
    profiles = {
        "cloud-primary": {
            "provider": "cloud",
            "model": "cloud-primary",
            "temperature": 0.7,
            "max_tokens": 128,
            "fallback_chain": ["direct-fallback"],
        },
        "global-fallback": {
            "provider": "local",
            "model": "global-fallback",
            "temperature": 0.2,
            "max_tokens": 64,
        },
        "direct-fallback": {
            "provider": "opencode",
            "model": "direct-fallback",
            "temperature": 0.2,
            "max_tokens": 64,
        },
    }
    cloud = AlwaysFailProvider("quota exhausted")
    global_fallback = LocalSuccessProvider("should not be used")
    direct_fallback = OpenAICompatSuccessProvider("inline fallback ok")

    monkeypatch.setattr(gateway_router_module, "MODEL_PROFILES", profiles)
    monkeypatch.setattr(gateway_router_module, "get_models_config", lambda: {})
    monkeypatch.setattr(
        gateway_router_module,
        "get_model_type_config",
        lambda model_type: {
            "primary": "cloud-primary",
            "fallback_on_explicit_profile": True,
            "fallback_chain": ["global-fallback"],
            "profiles": profiles,
        } if model_type == "llm" else {},
    )

    router = ModelGatewayRouter.__new__(ModelGatewayRouter)
    router._providers = {"cloud": cloud, "local": global_fallback, "opencode": direct_fallback}

    result = await router.chat(
        messages=[{"role": "user", "content": "hello"}],
        profile_key="cloud-primary",
        budget=RetryBudget(max_attempts=1),
    )

    assert result["content"] == "inline fallback ok"
    assert global_fallback.calls == 0
    assert direct_fallback.calls == 1
    assert result["diagnostics"]["candidates"] == ["cloud-primary", "direct-fallback"]


@pytest.mark.asyncio
async def test_chat_falls_back_on_auth_body_with_invalid_request_type(monkeypatch) -> None:
    profiles = {
        "gpt-5.5-knowledge": {
            "provider": "gptstore-text",
            "model": "gpt-5.5",
            "temperature": 0.2,
            "max_tokens": 128,
        },
        "deepseek-v4-flash": {
            "provider": "opencode",
            "model": "deepseek-v4-flash",
            "temperature": 0.7,
            "max_tokens": 128,
        },
    }
    gpt55 = AlwaysFailProvider(
        '{"error":{"code":"invalid_api_key","message":"missing or invalid API key","type":"invalid_request_error"}}',
        status_code=401,
    )
    deepseek = OpenAICompatSuccessProvider("deepseek auth fallback ok")

    monkeypatch.setattr(gateway_router_module, "MODEL_PROFILES", profiles)
    monkeypatch.setattr(
        gateway_router_module,
        "get_model_type_config",
        lambda model_type: {
            "primary": "gpt-5.5-knowledge",
            "fallback_on_explicit_profile": True,
            "fallback_chain": ["deepseek-v4-flash"],
            "profiles": profiles,
        } if model_type == "llm" else {},
    )

    router = ModelGatewayRouter.__new__(ModelGatewayRouter)
    router._providers = {"gptstore-text": gpt55, "opencode": deepseek}

    result = await router.chat(
        messages=[{"role": "user", "content": "hello"}],
        profile_key="gpt-5.5-knowledge",
        budget=RetryBudget(max_attempts=1),
    )

    assert result["content"] == "deepseek auth fallback ok"
    assert result["diagnostics"]["fallback_used"] is True
    assert result["diagnostics"]["selected_profile"] == "deepseek-v4-flash"


@pytest.mark.asyncio
async def test_chat_stops_fallback_on_protocol_error(monkeypatch) -> None:
    profiles = {
        "cloud-primary": {
            "provider": "cloud",
            "model": "cloud-primary",
            "temperature": 0.7,
            "max_tokens": 128,
        },
        "local-fallback": {
            "provider": "local",
            "model": "local-fallback",
            "temperature": 0.2,
            "max_tokens": 64,
        },
    }
    cloud = AlwaysFailProvider("tool_calls must be followed by tool messages")
    local = LocalSuccessProvider("should not run")

    monkeypatch.setattr(gateway_router_module, "MODEL_PROFILES", profiles)
    monkeypatch.setattr(
        gateway_router_module,
        "get_model_type_config",
        lambda model_type: {
            "primary": "cloud-primary",
            "fallback_on_explicit_profile": True,
            "fallback_chain": ["local-fallback"],
            "profiles": profiles,
        } if model_type == "llm" else {},
    )

    router = ModelGatewayRouter.__new__(ModelGatewayRouter)
    router._providers = {"cloud": cloud, "local": local}

    result = await router.chat(
        messages=[{"role": "user", "content": "hello"}],
        profile_key="cloud-primary",
        budget=RetryBudget(max_attempts=1),
    )

    assert "error" in result
    assert "tool_calls must be followed" in result["error"]
    assert result["diagnostics"]["attempts"][0]["profile"] == "cloud-primary"
    assert cloud.calls == 1
    assert local.calls == 0


@pytest.mark.asyncio
async def test_configured_llm_chain_keeps_global_default_and_exposes_gpt55_profile() -> None:
    llm_cfg = get_model_type_config("llm")
    vision_cfg = get_model_type_config("vision")
    profiles = llm_cfg["profiles"]
    vision_profiles = vision_cfg["profiles"]
    models_config = get_models_config()
    knowledge_routing = models_config["module_routing"]["knowledge"]
    fallback_policies = models_config["fallback_policies"]

    assert llm_cfg["primary"] == "deepseek-v4-flash"
    assert llm_cfg["fallback_chain"][:2] == ["gemma-4", "ollama-local"]
    assert profiles["deepseek-v4-flash"]["provider"] == "opencode"
    assert profiles["gpt-5.5-knowledge"]["provider"] == "gptstore-text"
    assert profiles["gpt-5.5-knowledge"]["retry_strategy"] == "fixed"
    assert profiles["gpt-5.5-knowledge"]["retry_delay_seconds"] == 30
    assert profiles["gpt-5.5-knowledge"]["fallback_policy"] == "knowledge_text_primary"
    assert fallback_policies["knowledge_text_primary"]["chain"] == ["deepseek-v4-flash"]
    assert vision_profiles["gpt-5.5-vision"]["fallback_policy"] == "knowledge_vision_primary"
    assert fallback_policies["knowledge_vision_primary"]["chain"] == ["mimo"]
    assert knowledge_routing["default_profile"] == "gpt-5.5-knowledge"
    assert knowledge_routing["fallback_profile"] == "deepseek-v4-flash"
    assert knowledge_routing["stages"]["raw_vision"] == "gpt-5.5-vision"
    assert get_model_type_config("vision")["primary"] == "gpt-5.5-vision"
    assert get_models_config()["providers"]["gptstore-text"]["session_affinity"]["scope"] == "request"
    assert get_models_config()["providers"]["gptstore-text"]["auth_recovery"] == {
        "strategy": "rotate_session",
        "status_codes": [401],
        "max_attempts": 3,
        "delay_seconds": 0.2,
    }


@pytest.mark.asyncio
async def test_cloud_auth_failure_falls_back_to_llama_with_diagnostics(monkeypatch) -> None:
    profiles = {
        "cloud-primary": {
            "provider": "cloud",
            "model": "cloud-primary",
            "temperature": 0.7,
            "max_tokens": 128,
        },
        "gemma-4": {
            "provider": "llama",
            "model": "gemma-4",
            "temperature": 0.2,
            "max_tokens": 64,
            "watchdog": "gemma-4",
        },
    }
    cloud = AlwaysFailProvider("invalid api key", status_code=401)
    llama = OpenAICompatSuccessProvider("llama fallback ok")

    async def ensure_ok(profile):
        return None

    monkeypatch.setattr(gateway_router_module, "MODEL_PROFILES", profiles)
    monkeypatch.setattr(gateway_router_module, "_ensure_local_text_model", ensure_ok)
    monkeypatch.setattr(
        gateway_router_module,
        "get_model_type_config",
        lambda model_type: {
            "primary": "cloud-primary",
            "fallback_on_explicit_profile": True,
            "fallback_chain": ["gemma-4"],
            "profiles": profiles,
        } if model_type == "llm" else {},
    )

    router = ModelGatewayRouter.__new__(ModelGatewayRouter)
    router._providers = {"cloud": cloud, "llama": llama}

    result = await router.chat(
        messages=[{"role": "user", "content": "hello"}],
        profile_key="cloud-primary",
        budget=RetryBudget(max_attempts=1),
    )

    assert result["content"] == "llama fallback ok"
    assert result["diagnostics"]["fallback_used"] is True
    assert result["diagnostics"]["selected_profile"] == "gemma-4"
    assert result["diagnostics"]["attempts"][0]["provider"] == "cloud"
    assert result["diagnostics"]["attempts"][0]["success"] is False
    assert result["diagnostics"]["attempts"][1]["provider"] == "llama"
    assert result["diagnostics"]["attempts"][1]["success"] is True


@pytest.mark.asyncio
async def test_cloud_5xx_retries_then_falls_back_to_llama(monkeypatch) -> None:
    profiles = {
        "cloud-primary": {
            "provider": "cloud",
            "model": "cloud-primary",
            "temperature": 0.7,
            "max_tokens": 128,
        },
        "gemma-4": {
            "provider": "llama",
            "model": "gemma-4",
            "temperature": 0.2,
            "max_tokens": 64,
            "watchdog": "gemma-4",
        },
    }
    cloud = AlwaysFailProvider("bad gateway", status_code=502)
    llama = OpenAICompatSuccessProvider("llama after 5xx ok")

    async def ensure_ok(profile):
        return None

    monkeypatch.setattr(gateway_router_module, "MODEL_PROFILES", profiles)
    monkeypatch.setattr(gateway_router_module, "_ensure_local_text_model", ensure_ok)
    monkeypatch.setattr(
        gateway_router_module,
        "get_model_type_config",
        lambda model_type: {
            "primary": "cloud-primary",
            "fallback_on_explicit_profile": True,
            "fallback_chain": ["gemma-4"],
            "profiles": profiles,
        } if model_type == "llm" else {},
    )

    router = ModelGatewayRouter.__new__(ModelGatewayRouter)
    router._providers = {"cloud": cloud, "llama": llama}

    result = await router.chat(
        messages=[{"role": "user", "content": "hello"}],
        profile_key="cloud-primary",
        budget=RetryBudget(max_attempts=2, base_delay_seconds=0.0),
    )

    assert result["content"] == "llama after 5xx ok"
    assert cloud.calls == 2
    assert llama.calls == 1
    assert result["diagnostics"]["fallback_used"] is True
    assert result["diagnostics"]["attempts"][0]["provider"] == "cloud"
    assert result["diagnostics"]["attempts"][0]["success"] is False
    assert result["diagnostics"]["attempts"][1]["provider"] == "llama"
    assert result["diagnostics"]["attempts"][1]["success"] is True


@pytest.mark.asyncio
async def test_llama_startup_failure_falls_through_to_ollama(monkeypatch) -> None:
    profiles = {
        "cloud-primary": {
            "provider": "cloud",
            "model": "cloud-primary",
            "temperature": 0.7,
            "max_tokens": 128,
        },
        "gemma-4": {
            "provider": "llama",
            "model": "gemma-4",
            "temperature": 0.2,
            "max_tokens": 64,
            "watchdog": "gemma-4",
        },
        "ollama-local": {
            "provider": "ollama",
            "model": "qwen2.5:7b",
            "temperature": 0.2,
            "max_tokens": 64,
        },
    }
    cloud = AlwaysFailProvider("quota exhausted", status_code=402)
    llama = OpenAICompatSuccessProvider("should not be called")
    ollama = OpenAICompatSuccessProvider("ollama fallback ok", provider_shape="ollama")

    async def ensure_fails(profile):
        raise FileNotFoundError("llama.cpp server binary is not configured")

    monkeypatch.setattr(gateway_router_module, "MODEL_PROFILES", profiles)
    monkeypatch.setattr(gateway_router_module, "_ensure_local_text_model", ensure_fails)
    monkeypatch.setattr(
        gateway_router_module,
        "get_model_type_config",
        lambda model_type: {
            "primary": "cloud-primary",
            "fallback_on_explicit_profile": True,
            "fallback_chain": ["gemma-4", "ollama-local"],
            "profiles": profiles,
        } if model_type == "llm" else {},
    )

    router = ModelGatewayRouter.__new__(ModelGatewayRouter)
    router._providers = {"cloud": cloud, "llama": llama, "ollama": ollama}

    result = await router.chat(
        messages=[{"role": "user", "content": "hello"}],
        profile_key="cloud-primary",
        budget=RetryBudget(max_attempts=1),
    )

    assert result["content"] == "ollama fallback ok"
    assert llama.calls == 0
    assert ollama.calls == 1
    assert result["diagnostics"]["attempts"][1]["stage"] == "health"
    assert result["diagnostics"]["attempts"][1]["provider"] == "llama"
    assert result["diagnostics"]["selected_profile"] == "ollama-local"


@pytest.mark.asyncio
async def test_local_fallback_exhaustion_returns_stable_diagnostics(monkeypatch) -> None:
    profiles = {
        "cloud-primary": {
            "provider": "cloud",
            "model": "cloud-primary",
            "temperature": 0.7,
            "max_tokens": 128,
        },
        "gemma-4": {
            "provider": "llama",
            "model": "gemma-4",
            "temperature": 0.2,
            "max_tokens": 64,
            "watchdog": "gemma-4",
        },
        "ollama-local": {
            "provider": "ollama",
            "model": "qwen2.5:7b",
            "temperature": 0.2,
            "max_tokens": 64,
        },
    }
    cloud = AlwaysFailProvider("quota exhausted", status_code=402)
    ollama = AlwaysFailProvider("connection refused", status_code=503)

    async def ensure_fails(profile):
        raise FileNotFoundError("Configured model file missing for gemma-4")

    monkeypatch.setattr(gateway_router_module, "MODEL_PROFILES", profiles)
    monkeypatch.setattr(gateway_router_module, "_ensure_local_text_model", ensure_fails)
    monkeypatch.setattr(
        gateway_router_module,
        "get_model_type_config",
        lambda model_type: {
            "primary": "cloud-primary",
            "fallback_on_explicit_profile": True,
            "fallback_chain": ["gemma-4", "ollama-local"],
            "profiles": profiles,
        } if model_type == "llm" else {},
    )

    router = ModelGatewayRouter.__new__(ModelGatewayRouter)
    router._providers = {"cloud": cloud, "ollama": ollama}

    result = await router.chat(
        messages=[{"role": "user", "content": "hello"}],
        profile_key="cloud-primary",
        budget=RetryBudget(max_attempts=1),
    )

    assert result["error"] == "connection refused"
    assert result["content"].startswith("(Model fallback exhausted:")
    diagnostics = result["diagnostics"]
    assert diagnostics["fallback_used"] is False
    assert "selected_profile" not in diagnostics
    assert diagnostics["candidates"] == ["cloud-primary", "gemma-4", "ollama-local"]
    assert [attempt["profile"] for attempt in diagnostics["attempts"]] == [
        "cloud-primary",
        "gemma-4",
        "ollama-local",
    ]
    assert diagnostics["attempts"][1]["stage"] == "health"
    assert "Configured model file missing" in diagnostics["attempts"][1]["error"]
    assert diagnostics["attempts"][2]["provider"] == "ollama"


@pytest.mark.asyncio
async def test_local_echo_provider_is_disabled_by_default() -> None:
    provider = LocalProvider()

    result = await provider.chat(
        messages=[{"role": "user", "content": "hello"}],
        model="local-test",
    )

    assert "error" in result
    assert await provider.check_health() is False


def test_watchdog_llama_launch_command_uses_configured_model_root(monkeypatch, tmp_path) -> None:
    model_file = tmp_path / "文本模型" / "demo.gguf"
    model_file.parent.mkdir()
    model_file.write_text("fake gguf", encoding="utf-8")
    monkeypatch.setenv("LLAMA_CPP_SERVER_BIN", "/bin/echo")
    monkeypatch.setattr(
        watchdog_launcher,
        "get_models_config",
        lambda: {
            "local_bin": {
                "llama_server_env": "LLAMA_CPP_SERVER_BIN",
                "model_root_env": "LOCAL_MODEL_ROOT",
                "model_root": str(tmp_path),
            }
        },
    )
    record = ModelRecord(
        name="demo",
        purpose="text",
        endpoint="http://127.0.0.1:39999",
        health_path="/v1/models",
        model_type="local",
        port=39999,
        launch={
            "backend": "llama.cpp",
            "model_path": "文本模型/demo.gguf",
            "args": ["-m", "{model_path}", "--port", "{port}"],
        },
    )

    command = watchdog_launcher._build_launch_command(record)

    assert command == ["/bin/echo", "-m", str(model_file), "--port", "39999"]


def test_watchdog_llama_launch_command_fails_fast_for_missing_model(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("LLAMA_CPP_SERVER_BIN", "/bin/echo")
    monkeypatch.setattr(
        watchdog_launcher,
        "get_models_config",
        lambda: {
            "local_bin": {
                "llama_server_env": "LLAMA_CPP_SERVER_BIN",
                "model_root": str(tmp_path),
            }
        },
    )
    record = ModelRecord(
        name="missing-demo",
        purpose="text",
        endpoint="http://127.0.0.1:39999",
        health_path="/v1/models",
        model_type="local",
        port=39999,
        launch={
            "backend": "llama.cpp",
            "model_path": "文本模型/missing.gguf",
        },
    )

    with pytest.raises(FileNotFoundError, match="Configured model file missing"):
        watchdog_launcher._build_launch_command(record)


@pytest.mark.asyncio
async def test_describe_image_falls_back_from_explicit_vision_profile(monkeypatch) -> None:
    profiles = {
        "mimo": {
            "provider": "mimo",
            "model": "mimo-v2.5",
            "temperature": 0.7,
            "max_tokens": 128,
        },
        "qwen3-vl": {
            "provider": "local",
            "model": "qwen3-vl",
            "temperature": 0.2,
            "max_tokens": 64,
        },
    }
    mimo = AlwaysFailProvider("vision quota exhausted")
    local = LocalSuccessProvider("本地视觉描述")

    monkeypatch.setattr(gateway_router_module, "_VISION_PRIMARY", "mimo")
    monkeypatch.setattr(gateway_router_module, "_VISION_FALLBACK", ["qwen3-vl"])
    monkeypatch.setattr(gateway_router_module, "_VISION_PROFILES", profiles)
    monkeypatch.setattr(
        gateway_router_module,
        "get_model_type_config",
        lambda model_type: {
            "primary": "mimo",
            "fallback_on_explicit_profile": True,
            "fallback_chain": ["qwen3-vl"],
            "profiles": profiles,
        } if model_type == "vision" else {},
    )

    router = ModelGatewayRouter.__new__(ModelGatewayRouter)
    router._providers = {"mimo": mimo, "local": local}

    result = await router.describe_image(
        image_bytes=b"not-really-an-image",
        profile_key="mimo",
        mime_type="image/png",
    )

    assert result == "本地视觉描述"
    assert mimo.calls == 1
    assert local.calls == 1
