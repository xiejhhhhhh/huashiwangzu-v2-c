from functools import lru_cache
from pathlib import Path

from pydantic import model_validator
from pydantic_settings import BaseSettings

BACKEND_DIR = Path(__file__).resolve().parents[1]
PROJECT_ROOT = BACKEND_DIR.parent
BACKEND_ENV_FILE = BACKEND_DIR / ".env"


class Settings(BaseSettings):
    # Database（密码必须通过 .env 或环境变量设置）
    DB_HOST: str = "127.0.0.1"
    DB_PORT: int = 5432
    DB_USER: str = "postgres"
    DB_PASSWORD: str = ""
    DB_NAME: str = "华世王镞_v2"
    DB_IDLE_IN_TRANSACTION_TIMEOUT_MS: int = 60000
    DB_USE_NULL_POOL: bool = False
    DB_POOL_SIZE: int = 20
    DB_MAX_OVERFLOW: int = 10
    DB_POOL_TIMEOUT: int = 120
    DB_POOL_RECYCLE_SECONDS: int = 1800

    @property
    def DATABASE_URL(self) -> str:
        return (
            f"postgresql+asyncpg://{self.DB_USER}:{self.DB_PASSWORD}"
            f"@{self.DB_HOST}:{self.DB_PORT}/{self.DB_NAME}"
        )

    # JWT（密钥必须通过 .env 或环境变量设置）
    JWT_SECRET: str = ""
    JWT_ALGORITHM: str = "HS256"
    JWT_EXPIRE_MINUTES: int = 1440

    # Server（仅监听本机，不暴露给局域网）
    APP_HOST: str = "127.0.0.1"
    APP_PORT: int = 33000
    APP_DEBUG: bool = False

    # CORS
    CORS_ORIGINS: list[str] = ["http://127.0.0.1:5173", "http://localhost:5173"]

    UPLOAD_DIR: str = "data/uploads"
    MAX_PREVIEW_SIZE: int = 1 * 1024 * 1024
    STORAGE_ROOT: str = "data/uploads"
    ENTERPRISE_SOURCE_ALLOWED_ROOTS: str = f"~:{Path('/Volumes')}"

    MODEL_WATCHDOG_ENABLED: bool = True
    MODEL_WATCHDOG_POLL_INTERVAL: float = 2.0
    MODEL_WATCHDOG_TIMEOUT: int = 120
    LLAMA_SERVER_BIN: str = ""    # 必填：llama-server 可执行文件路径
    AI_MODEL_ROOT: str = ""       # 必填：本地模型文件存放根目录

    # Office conversion worker guardrails
    OFFICE_CONVERSION_MAX_CONCURRENT: int = 8
    OFFICE_CONVERSION_TIMEOUT_SECONDS: int = 180
    OFFICE_CONVERSION_TERMINATE_GRACE_SECONDS: float = 5.0

    # API 密钥（必须通过 .env 或环境变量设置）
    MIMO_GATE1_KEY: str = ""
    DEEPSEEK_API_KEY: str = ""

    # GPTStore 中转站（图片生成 / 可选文本模型）
    GPTSTORE_API_KEY: str = ""
    GPTSTORE_BASE_URL: str = "https://pool.gptstore.club/v1"
    GPTSTORE_PROXY: str = ""

    # grok-4.5 本地中转（openai chat 协议，端口 8317，一千号并发定类/确认用）
    GROK_API_KEY: str = ""

    # ant 协议(Anthropic /v1/messages)备用服务商,不参与常规运行,填了 key 才启用
    DEEPSEEK_ANTHROPIC_KEY: str = ""   # deepseek 官方 anthropic 端点
    JAYCE_CLAUDE_KEY: str = ""         # jayce 中转站 claude(需走代理)

    # LiblibAI（生图模块）
    LIBLIB_ACCESS_KEY: str = ""
    LIBLIB_SECRET_KEY: str = ""

    model_config = {"env_file": BACKEND_ENV_FILE, "env_file_encoding": "utf-8", "extra": "ignore"}

    @model_validator(mode="after")
    def _validate_secrets(self):
        """确保 JWT_SECRET 通过 .env 设置，不允许空密钥启动"""
        if not self.JWT_SECRET:
            raise ValueError(
                "JWT_SECRET is empty — must be set via .env or environment variable"
            )
        self.UPLOAD_DIR = self._resolve_project_path(self.UPLOAD_DIR)
        self.STORAGE_ROOT = self._resolve_project_path(self.STORAGE_ROOT)
        return self

    @staticmethod
    def _resolve_project_path(value: str) -> str:
        path = Path(value).expanduser()
        if not path.is_absolute():
            path = PROJECT_ROOT / path
        return str(path.resolve())


@lru_cache
def get_settings() -> Settings:
    return Settings()
