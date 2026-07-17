import sys

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from app.config import get_settings

settings = get_settings()

_engine_kwargs = {
    "echo": settings.APP_DEBUG,
    "connect_args": {
        "server_settings": {
            "idle_in_transaction_session_timeout": str(settings.DB_IDLE_IN_TRANSACTION_TIMEOUT_MS),
        },
    },
}

# 是否为一次性 executor 子进程(dispatcher 用 `python -m app.task_worker_main --executor-task-id N` 派生)。
# executor 只跑一个任务就退出,不需要常驻大池;继承后端的 pool_size=120 会导致 N 个并发 executor
# 各开一个大池 → 瞬间打爆 PG max_connections=300(too many clients)。executor 强制用极小池。
_IS_EXECUTOR = "--executor-task-id" in sys.argv

if settings.DB_USE_NULL_POOL or "pytest" in sys.modules:
    _engine_kwargs["poolclass"] = NullPool
elif _IS_EXECUTOR:
    # 一次性 executor:极小池,单任务够用,防止多并发 executor 累加爆连接。
    _engine_kwargs.update({
        "pool_size": 2,
        "max_overflow": 2,
        "pool_timeout": max(1, settings.DB_POOL_TIMEOUT),
        "pool_recycle": max(60, settings.DB_POOL_RECYCLE_SECONDS),
        "pool_pre_ping": True,
    })
else:
    _engine_kwargs.update({
        "pool_size": max(1, settings.DB_POOL_SIZE),
        "max_overflow": max(0, settings.DB_MAX_OVERFLOW),
        "pool_timeout": max(1, settings.DB_POOL_TIMEOUT),
        "pool_recycle": max(60, settings.DB_POOL_RECYCLE_SECONDS),
        "pool_pre_ping": True,
    })

engine = create_async_engine(settings.DATABASE_URL, **_engine_kwargs)

AsyncSessionLocal = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)


async def get_db():
    async with AsyncSessionLocal() as session:
        yield session


async def init_db():
    async with engine.begin() as conn:
        from app.models.base import Base
        await conn.run_sync(Base.metadata.create_all)


async def dispose_db():
    await engine.dispose()
