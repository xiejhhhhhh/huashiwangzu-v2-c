import pytest
from app.services.agent.gateway.adapters import (
    DeepSeekAdapter,
    GemmaAdapter,
    QwenAdapter,
    OpenAICompatAdapter,
    get_adapter,
    list_adapters,
)


class TestDeepSeekAdapter:
    adapter = DeepSeekAdapter()

    def test_adapt_response_opencode(self):
        raw = {
            "choices": [{
                "index": 0,
                "message": {
                    "role": "assistant",
                    "content": "答案是14",
                    "reasoning_content": "3的平方=9, 9+5=14",
                },
                "finish_reason": "stop",
            }],
        }
        result = self.adapter.adapt_response(raw, provider="opencode")
        assert result["content"] == "答案是14"
        assert result["thinking"] == "3的平方=9, 9+5=14"
        assert result["finish_reason"] == "stop"
        assert result["tool_calls"] == []

    def test_adapt_response_ollama(self):
        raw = {
            "message": {
                "role": "assistant",
                "content": "答案是14",
                "reasoning_content": "3的平方=9, 9+5=14",
            },
            "done_reason": "stop",
            "done": True,
        }
        result = self.adapter.adapt_response(raw, provider="ollama")
        assert result["content"] == "答案是14"
        assert result["thinking"] == "3的平方=9, 9+5=14"

    def test_adapt_stream_chunk_openai_token(self):
        chunk = {"choices": [{"delta": {"content": "14"}}]}
        event = self.adapter.adapt_stream_chunk(chunk, provider="opencode")
        assert event["type"] == "token"
        assert event["content"] == "14"

    def test_adapt_stream_chunk_openai_thinking(self):
        chunk = {"choices": [{"delta": {"reasoning_content": "3的平方=9"}}]}
        event = self.adapter.adapt_stream_chunk(chunk, provider="opencode")
        assert event["type"] == "thinking"
        assert event["content"] == "3的平方=9"

    def test_adapt_stream_chunk_openai_done(self):
        chunk = {"choices": [{"delta": {}, "finish_reason": "stop"}]}
        event = self.adapter.adapt_stream_chunk(chunk, provider="opencode")
        assert event["type"] == "done"

    def test_adapt_stream_chunk_ollama_token(self):
        chunk = {"message": {"content": "14"}, "done": False}
        event = self.adapter.adapt_stream_chunk(chunk, provider="ollama")
        assert event["type"] == "token"
        assert event["content"] == "14"

    def test_adapt_stream_chunk_ollama_done(self):
        chunk = {"message": {"content": ""}, "done": True}
        event = self.adapter.adapt_stream_chunk(chunk, provider="ollama")
        assert event["type"] == "done"


class TestGemmaAdapter:
    adapter = GemmaAdapter()

    def test_adapt_response_no_thinking(self):
        raw = {
            "message": {"role": "assistant", "content": "答案是14"},
            "done_reason": "stop",
            "done": True,
        }
        result = self.adapter.adapt_response(raw, provider="ollama")
        assert result["content"] == "答案是14"
        assert result["thinking"] == ""

    def test_adapt_stream_chunk_token(self):
        chunk = {"message": {"content": "答"}, "done": False}
        event = self.adapter.adapt_stream_chunk(chunk, provider="ollama")
        assert event["type"] == "token"
        assert event["content"] == "答"


class TestQwenAdapter:
    adapter = QwenAdapter()

    def test_adapt_response_no_thinking(self):
        raw = {
            "choices": [{
                "index": 0,
                "message": {"role": "assistant", "content": "14"},
                "finish_reason": "stop",
            }],
        }
        result = self.adapter.adapt_response(raw, provider="opencode")
        assert result["content"] == "14"
        assert result["thinking"] == ""


class TestOpenAICompatAdapter:
    adapter = OpenAICompatAdapter()

    def test_adapt_response_with_thinking(self):
        raw = {
            "choices": [{
                "index": 0,
                "message": {
                    "content": "答案是14",
                    "reasoning_content": "3的平方=9, 9+5=14",
                },
                "finish_reason": "stop",
            }],
        }
        result = self.adapter.adapt_response(raw, provider="opencode")
        assert result["content"] == "答案是14"
        assert result["thinking"] == "3的平方=9, 9+5=14"

    def test_adapt_response_ollama_fallback(self):
        raw = {"message": {"role": "assistant", "content": "14"}}
        result = self.adapter.adapt_response(raw, provider="ollama")
        assert result["content"] == "14"
        assert result["thinking"] == ""


class TestRegistry:
    def test_get_adapter_by_exact_name(self):
        adapter = get_adapter("deepseek-v4-flash")
        assert isinstance(adapter, DeepSeekAdapter)

    def test_get_adapter_gemma(self):
        adapter = get_adapter("gemma-4")
        assert isinstance(adapter, GemmaAdapter)

    def test_get_adapter_qwen(self):
        adapter = get_adapter("qwen-72b")
        assert isinstance(adapter, QwenAdapter)

    def test_get_adapter_fallback(self):
        assert isinstance(get_adapter("unknown-model-xyz"), OpenAICompatAdapter)
        assert isinstance(get_adapter(""), OpenAICompatAdapter)

    def test_list_adapters(self):
        entries = list_adapters()
        names = [e["model"] for e in entries]
        assert "deepseek-v4-flash" in names and "gemma-4" in names
        assert "qwen-72b" in names and "__default__" in names
