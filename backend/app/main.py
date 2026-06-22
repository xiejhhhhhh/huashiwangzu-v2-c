import logging
from pathlib import Path
from contextlib import asynccontextmanager
from fastapi import FastAPI
from sqlalchemy import text

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s %(message)s",
    datefmt="%H:%M:%S",
)
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from app.config import get_settings
from app.database import init_db, dispose_db
from app.core.handlers import register_exception_handlers
from app.middleware.logging_middleware import RequestLoggingMiddleware
from app.routers.registry import register_routers

config = get_settings()
FRONTEND_DIST = Path(__file__).parent.parent.parent / "frontend" / "dist"


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()

    # Idempotent migration: add scheduling columns to SystemTaskQueue
    from app.models.system import (ensure_framework_scheduling_columns, ensure_usage_daily_table,
                                     ensure_agent_configs_table, ensure_approval_queue_table)
    await ensure_framework_scheduling_columns()
    await ensure_usage_daily_table()
    await ensure_agent_configs_table()
    await ensure_approval_queue_table()

    # Set up module-specific log files
    from app.services.module_logger import setup_module_logging
    setup_module_logging()

    from app.database import AsyncSessionLocal
    from app.services.app_service import sync_apps_from_manifest
    from app.services.task_worker import start_worker, stop_worker

    async with AsyncSessionLocal() as db:
        result = await sync_apps_from_manifest(db)
        logging.getLogger(__name__).info("App manifest sync completed: %s", result)

    start_worker()
    logging.getLogger(__name__).info("Background task worker started")

    # After modules are loaded, set up per-module file handlers
    from app.services.module_logger import setup_v2_loggers_for_modules
    setup_v2_loggers_for_modules()

    yield
    await stop_worker()
    await dispose_db()


app = FastAPI(
    title="Huashi Wangzu V2 API",
    version="2.0.0",
    lifespan=lifespan,
)

# 暴露前端 dist 路径给异常处理器，用于 SPA 404 兜底
app.state.frontend_dist = FRONTEND_DIST if FRONTEND_DIST.exists() else None

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=config.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Request logging
app.add_middleware(RequestLoggingMiddleware)

# ── Module self-heal (intercepts requests to broken modules, tries to recover) ──
from app.middleware.module_self_heal import ModuleSelfHealMiddleware
app.add_middleware(ModuleSelfHealMiddleware, fastapi_app=app)

# ── Request timeout (SSE endpoints exempt) ──
from app.middleware.timeout_middleware import TimeoutMiddleware
app.add_middleware(TimeoutMiddleware)

# ── Request ID (per-request UUID, injected into all logs) ──
from app.middleware.request_id import RequestIdMiddleware
app.add_middleware(RequestIdMiddleware)

# Exception handlers
register_exception_handlers(app)

# Routers
register_routers(app)


@app.get("/api/health")
async def health_check():
    from app.database import engine
    from app.schemas.common import ApiResponse
    from app.routers.registry import get_module_load_errors
    from app.services.task_worker import worker_health

    database_status = "ok"
    try:
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
    except Exception:
        database_status = "unreachable"

    module_errors = get_module_load_errors()
    return ApiResponse(data={
        "status": "ok",
        "version": "2.0.0",
        "database": database_status,
        "module_errors": module_errors if module_errors else None,
        "worker": worker_health(),
    })


# ── Serve Vue frontend static files ──
if FRONTEND_DIST.exists():
    app.mount("/assets", StaticFiles(directory=str(FRONTEND_DIST / "assets")), name="assets")
