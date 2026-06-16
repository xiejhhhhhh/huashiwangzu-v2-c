from typing import Literal

ModelType = Literal["local", "cloud"]
ModelPurpose = Literal["嵌入", "重排", "视觉", "文本"]


class ModelRecord:
    def __init__(
        self,
        name: str,
        purpose: ModelPurpose,
        endpoint: str,
        health_path: str,
        model_type: ModelType,
        startup_script: str = "",
        port: int = 0,
        description: str = "",
    ):
        self.name = name
        self.purpose = purpose
        self.endpoint = endpoint
        self.health_path = health_path
        self.model_type = model_type
        self.startup_script = startup_script
        self.port = port
        self.description = description

    def health_url(self) -> str:
        return f"{self.endpoint.rstrip('/')}/{self.health_path.lstrip('/')}"

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "purpose": self.purpose,
            "endpoint": self.endpoint,
            "health_path": self.health_path,
            "model_type": self.model_type,
            "startup_script": self.startup_script,
            "port": self.port,
            "description": self.description,
        }


_REGISTRY: dict[str, ModelRecord] = {}


def register(record: ModelRecord) -> None:
    _REGISTRY[record.name] = record


def get_model(name: str) -> ModelRecord:
    record = _REGISTRY.get(name)
    if not record:
        raise KeyError(f"Model '{name}' not found in registry")
    return record


def list_models() -> list[ModelRecord]:
    return list(_REGISTRY.values())


def list_local_models() -> list[ModelRecord]:
    return [m for m in _REGISTRY.values() if m.model_type == "local"]


register(ModelRecord(
    name="bge-m3",
    purpose="嵌入",
    endpoint="http://127.0.0.1:30000",
    health_path="/v1/models",
    model_type="local",
    startup_script="start_bge_m3_embedding.sh",
    port=30000,
    description="BGE-M3 嵌入模型，提供向量嵌入能力",
))

register(ModelRecord(
    name="bge-reranker",
    purpose="重排",
    endpoint="http://127.0.0.1:30001",
    health_path="/v1/models",
    model_type="local",
    startup_script="start_bge_reranker.sh",
    port=30001,
    description="BGE-Reranker-V2-M3 重排模型，用于文本相关性排序",
))

register(ModelRecord(
    name="qwen3-vl",
    purpose="视觉",
    endpoint="http://127.0.0.1:30002",
    health_path="/v1/models",
    model_type="local",
    startup_script="start_qwen3_vl_vision.sh",
    port=30002,
    description="Qwen3VL-8B 视觉语言模型，支持图片分析",
))

register(ModelRecord(
    name="gemma-4",
    purpose="文本",
    endpoint="http://127.0.0.1:30003",
    health_path="/v1/models",
    model_type="local",
    startup_script="start_gemma4_text.sh",
    port=30003,
    description="Gemma-4-26B 文本模型，唯一本地文本模型",
))

register(ModelRecord(
    name="opencode-go",
    purpose="文本",
    endpoint="https://opencode.ai/zen/go/v1",
    health_path="/chat/completions",
    model_type="cloud",
    startup_script="",
    port=0,
    description="OpenCode Go 订阅模型（deepseek-v4-flash），密钥来自 DEEPSEEK_API_KEY",
))

register(ModelRecord(
    name="mimo",
    purpose="视觉",
    endpoint="https://token-plan-cn.xiaomimimo.com/v1",
    health_path="/chat/completions",
    model_type="cloud",
    startup_script="",
    port=0,
    description="MiMo 云端多模态模型（mimo-v2.5），支持图片分析。实测 4 门全部连通（Gate1 中国区 + Gate2~4 新加坡）",
))
