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

if settings.DB_USE_NULL_POOL or "pytest" in sys.modules:
    _engine_kwargs["poolclass"] = NullPool
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
