from pathlib import Path
from pydantic_settings import BaseSettings
from functools import lru_cache


class Settings(BaseSettings):
    # Database（密码必须通过 .env 或环境变量设置）
    DB_HOST: str = "127.0.0.1"
    DB_PORT: int = 5432
    DB_USER: str = "postgres"
    DB_PASSWORD: str = ""
    DB_NAME: str = "华世王镞_v2"

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
    APP_PORT: int = 30004
    APP_DEBUG: bool = True

    # CORS
    CORS_ORIGINS: list[str] = ["*"]

    UPLOAD_DIR: str = "data/uploads"
    MAX_PREVIEW_SIZE: int = 1 * 1024 * 1024
    STORAGE_ROOT: str = "data/uploads"

    MODEL_WATCHDOG_ENABLED: bool = True
    MODEL_WATCHDOG_POLL_INTERVAL: float = 2.0
    MODEL_WATCHDOG_TIMEOUT: int = 120
    LLAMA_SERVER_BIN: str = ""    # 必填：llama-server 可执行文件路径
    AI_MODEL_ROOT: str = ""       # 必填：本地模型文件存放根目录

    # API 密钥（必须通过 .env 或环境变量设置）
    MIMO_GATE1_KEY: str = ""
    DEEPSEEK_API_KEY: str = ""

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}


@lru_cache
def get_settings() -> Settings:
    return Settings()
