from .base import ModelAdapter
from .deepseek import DeepSeekAdapter
from .gemma import GemmaAdapter
from .qwen import QwenAdapter
from .openai_compat import OpenAICompatAdapter

# ============================================================
# 如何添加新模型（扩展接口说明）
# ============================================================
# 加一个新模型只需 2 步，不改其他代码：
#
# 1. 在 adapters/ 下创建适配器文件（如 mymodel.py）：
#    class MyModelAdapter(ModelAdapter):
#        def adapt_response(self, raw, provider=""): ...
#        def adapt_stream_chunk(self, chunk, provider=""): ...
#
# 2. 在本文件 ADAPTER_REGISTRY 中注册一行：
#    "my-model-name": MyModelAdapter,
#
# 适配器职责：从模型原始返回 JSON 中提取统一的
# {content, thinking, tool_calls, finish_reason} 四个字段。
# 流式和非流式接口都要实现。
#
# 看 provider 参数区分响应格式：
#   - "llama":    OpenAI-compatible llama-server response.
#   - "opencode": OpenAI-compatible OpenCode Go response.
#
# 常用字段映射：
#   DeepSeek: message.reasoning_content → thinking
#   Gemma:    无 thinking 字段 → thinking=""
#   Qwen:     无 thinking 字段 → thinking=""
#   OpenAI 兼容: choice.message.reasoning_content → thinking
# ============================================================

_ADAPTER_CACHE: dict[str, ModelAdapter] = {}

ADAPTER_REGISTRY: dict[str, type[ModelAdapter]] = {
    "deepseek-v4-flash": DeepSeekAdapter,
    "deepseek-v4-pro": DeepSeekAdapter,
    "gemma-4": GemmaAdapter,
    "qwen-72b": QwenAdapter,
    "qwen2.5-14b": QwenAdapter,
    "__default__": OpenAICompatAdapter,
}


def get_adapter(model_name: str) -> ModelAdapter:
    name_lower = model_name.lower()
    if not name_lower:
        if "__default__" not in _ADAPTER_CACHE:
            _ADAPTER_CACHE["__default__"] = OpenAICompatAdapter()
        return _ADAPTER_CACHE["__default__"]
    for key, adapter_cls in ADAPTER_REGISTRY.items():
        if key == "__default__":
            continue
        if key == name_lower or key in name_lower or name_lower in key:
            if key not in _ADAPTER_CACHE:
                _ADAPTER_CACHE[key] = adapter_cls()
            return _ADAPTER_CACHE[key]
    if "__default__" not in _ADAPTER_CACHE:
        _ADAPTER_CACHE["__default__"] = OpenAICompatAdapter()
    return _ADAPTER_CACHE["__default__"]


def register_adapter(model_name: str, adapter_cls: type[ModelAdapter]) -> None:
    ADAPTER_REGISTRY[model_name] = adapter_cls
    _ADAPTER_CACHE.pop(model_name, None)


def list_adapters() -> list[dict]:
    return [
        {"model": k, "adapter": v.__name__}
        for k, v in ADAPTER_REGISTRY.items()
    ]


def clear_cache() -> None:
    _ADAPTER_CACHE.clear()
