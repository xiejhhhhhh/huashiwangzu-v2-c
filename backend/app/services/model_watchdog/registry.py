from typing import Literal

from app.gateway.config import (
    get_models_config,
    get_models_config_path,
    get_watchdog_model_configs,
)

ModelType = Literal["local", "cloud"]
ModelPurpose = str  # "embedding" | "rerank" | "vision" | "text" (English, from models.json)


class ModelRecord:
    def __init__(
        self,
        name: str,
        purpose: str,
        endpoint: str,
        health_path: str,
        model_type: ModelType,
        startup_script: str = "",
        port: int = 0,
        description: str = "",
        launch: dict | None = None,
        auto_unload: bool = False,
        idle_timeout_seconds: int = 0,
        launch_timeout_seconds: int = 0,
        startup_stall_timeout_seconds: int = 0,
        max_startup_seconds: int = 0,
    ):
        self.name = name
        self.purpose = purpose
        self.endpoint = endpoint
        self.health_path = health_path
        self.model_type = model_type
        self.startup_script = startup_script
        self.port = port
        self.description = description
        self.launch = launch or {}
        self.auto_unload = auto_unload
        self.idle_timeout_seconds = idle_timeout_seconds
        self.launch_timeout_seconds = launch_timeout_seconds
        self.startup_stall_timeout_seconds = startup_stall_timeout_seconds
        self.max_startup_seconds = max_startup_seconds

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
            "launch": self.launch,
            "auto_unload": self.auto_unload,
            "idle_timeout_seconds": self.idle_timeout_seconds,
            "launch_timeout_seconds": self.launch_timeout_seconds,
            "startup_stall_timeout_seconds": self.startup_stall_timeout_seconds,
            "max_startup_seconds": self.max_startup_seconds,
        }


_REGISTRY: dict[str, ModelRecord] = {}


def _load_from_config() -> None:
    """Load watchdog_models from models.json (single source of truth)."""
    config_path = get_models_config_path()
    if not config_path.exists():
        raise FileNotFoundError(
            f"models.json not found at {config_path}. "
            "Cannot initialize model registry."
        )

    models_config = get_models_config()
    watchdog_defaults = models_config.get("watchdog_defaults", {})
    watchdog_models = get_watchdog_model_configs()
    if not watchdog_models:
        raise ValueError(
            f"'watchdog_models' section missing or empty in {config_path}"
        )

    _REGISTRY.clear()
    for name, info in watchdog_models.items():
        auto_unload = bool(info.get("auto_unload", watchdog_defaults.get("auto_unload", False)))
        idle_timeout_seconds = int(
            info.get(
                "idle_timeout_seconds",
                watchdog_defaults.get("idle_timeout_seconds", 0),
            )
            or 0
        )
        launch_timeout_seconds = int(
            info.get(
                "launch_timeout_seconds",
                watchdog_defaults.get("launch_timeout", 0),
            )
            or 0
        )
        startup_stall_timeout_seconds = int(
            info.get(
                "startup_stall_timeout_seconds",
                watchdog_defaults.get("startup_stall_timeout_seconds", 0),
            )
            or 0
        )
        max_startup_seconds = int(
            info.get(
                "max_startup_seconds",
                watchdog_defaults.get("max_startup_seconds", 0),
            )
            or 0
        )
        record = ModelRecord(
            name=name,
            purpose=info.get("purpose", ""),
            endpoint=info.get("endpoint", ""),
            health_path=info.get("health_path", ""),
            model_type=info.get("model_type", "local"),
            startup_script=info.get("startup_script", ""),
            port=info.get("port", 0),
            description=info.get("description", ""),
            launch=info.get("launch") or {},
            auto_unload=auto_unload,
            idle_timeout_seconds=idle_timeout_seconds,
            launch_timeout_seconds=launch_timeout_seconds,
            startup_stall_timeout_seconds=startup_stall_timeout_seconds,
            max_startup_seconds=max_startup_seconds,
        )
        _REGISTRY[name] = record


# Initialize registry from config file at import time
_load_from_config()


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
