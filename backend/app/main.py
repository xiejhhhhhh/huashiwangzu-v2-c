import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from sqlalchemy import text

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.config import get_settings
from app.core.handlers import register_exception_handlers
from app.database import dispose_db, init_db
from app.middleware.logging_middleware import RequestLoggingMiddleware
from app.routers.registry import register_routers

config = get_settings()
FRONTEND_DIST = Path(__file__).parent.parent.parent / "frontend" / "dist"


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()

    # Idempotent migration: add scheduling columns to SystemTaskQueue
    from app.models.system import ensure_framework_scheduling_columns
    await ensure_framework_scheduling_columns()

    # Idempotent migration: add origin_type to framework_content_packages
    from sqlalchemy import text as sa_text

    from app.database import engine
    try:
        async with engine.begin() as conn:
            await conn.execute(sa_text(
                "ALTER TABLE framework_content_packages "
                "ADD COLUMN IF NOT EXISTS origin_type VARCHAR(32) DEFAULT 'uploaded'"
            ))
            logger.info("Ensured origin_type column on framework_content_packages")
    except Exception as e:
        logger.warning("Migration origin_type skipped: %s", e)

    # Set up module-specific log files
    from app.services.module_logger import setup_module_logging
    setup_module_logging()

    from app.database import AsyncSessionLocal
    from app.services.app_service import sync_apps_from_manifest
    from app.services.private_module_service import restore_active_private_modules, set_app_instance
    from app.services.task_worker import start_worker, stop_worker

    # Register private module service app reference
    set_app_instance(app)

    async with AsyncSessionLocal() as db:
        result = await sync_apps_from_manifest(db)
        logger.info("App manifest sync completed: %s", result)
        private_restore = await restore_active_private_modules(db)
        if private_restore["restored"] or private_restore["failed"]:
            logger.info("Private module runtime restore completed: %s", private_restore)

    start_worker()
    logger.info("Background task worker started")

    # After modules are loaded, set up per-module file handlers
    from app.services.module_logger import setup_v2_loggers_for_modules
    setup_v2_loggers_for_modules()

    # Initialize event bus (create event_log table, start retry scheduler)
    import asyncio

    from app.services.event_bus import _ensure_event_log_table, retry_failed_events
    await _ensure_event_log_table()
    await retry_failed_events()

    # Periodic event retry (every 60 seconds)
    async def _event_retry_loop():
        while True:
            try:
                await asyncio.sleep(60)
                await retry_failed_events()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.warning("Event retry loop error: %s", e)
    _retry_task = asyncio.create_task(_event_retry_loop())
    app.state._event_retry_task = _retry_task

    yield
    if hasattr(app.state, "_event_retry_task"):
        app.state._event_retry_task.cancel()
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
    from app.routers.registry import get_module_load_errors
    from app.schemas.common import ApiResponse
    from app.services.task_worker import worker_health

    database_status = "ok"
    task_queue_summary = None
    try:
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
            task_rows = await conn.execute(text("""
                SELECT status, count(*)
                FROM framework_system_task_queues
                WHERE status IN ('pending', 'running', 'failed')
                GROUP BY status
            """))
            task_counts = {row[0]: int(row[1]) for row in task_rows.fetchall()}
            semantic_failed_completed_24h = await conn.execute(text("""
                SELECT count(*)
                FROM framework_system_task_queues
                WHERE status = 'completed'
                  AND completed_at >= NOW() - INTERVAL '24 hours'
                  AND result IS NOT NULL
                  AND (result ILIKE '%"error"%' OR result ILIKE '%"status": "failed"%')
            """))
            semantic_failed_completed_total = await conn.execute(text("""
                SELECT count(*)
                FROM framework_system_task_queues
                WHERE status = 'completed'
                  AND result IS NOT NULL
                  AND (
                    result ILIKE '%"success": false%'
                    OR result ILIKE '%"status": "failed"%'
                    OR result ILIKE '%"status":"failed"%'
                    OR (
                      result ILIKE '%"error"%'
                      AND result NOT ILIKE '%"success": true%'
                    )
                  )
            """))
            task_queue_summary = {
                "pending": task_counts.get("pending", 0),
                "running": task_counts.get("running", 0),
                "failed": task_counts.get("failed", 0),
                "historical_failed_debt": task_counts.get("failed", 0),
                "semantic_failed_completed_24h": int(semantic_failed_completed_24h.scalar() or 0),
                "semantic_failed_completed_total": int(semantic_failed_completed_total.scalar() or 0),
            }
            task_queue_summary["debt_status"] = (
                "debt"
                if (
                    task_queue_summary["historical_failed_debt"] > 0
                    or task_queue_summary["semantic_failed_completed_total"] > 0
                )
                else "clean"
            )
    except Exception:
        database_status = "unreachable"

    module_errors = get_module_load_errors()

    # Event bus health: verify connectivity AND no stuck processing events
    event_bus_ok = True
    event_bus_stuck_processing = 0
    try:
        from app.services.event_bus import PROCESSING_TIMEOUT_SECONDS, get_event_log
        await get_event_log(limit=1)
        # Detect events that are stuck in processing beyond the lease timeout
        async with engine.connect() as conn:
            stuck = await conn.execute(text(f"""
                SELECT count(*)
                FROM framework_event_log
                WHERE status = 'processing'
                  AND processing_started_at IS NOT NULL
                  AND processing_started_at < NOW() - ({PROCESSING_TIMEOUT_SECONDS} * INTERVAL '1 second')
            """))
            event_bus_stuck_processing = int(stuck.scalar() or 0)
            if event_bus_stuck_processing > 0:
                event_bus_ok = False
    except Exception:
        event_bus_ok = False

    worker = worker_health()
    event_bus_status = "ok" if event_bus_ok else "error"
    task_queue_ok = not (
        task_queue_summary
        and task_queue_summary.get("semantic_failed_completed_24h", 0) > 0
    )
    status = "ok"
    if (
        database_status != "ok"
        or module_errors
        or not worker.get("running")
        or event_bus_status != "ok"
        or not task_queue_ok
    ):
        status = "degraded" if database_status == "ok" else "error"

    return ApiResponse(data={
        "status": status,
        "version": "2.0.0",
        "database": database_status,
        "module_errors": module_errors if module_errors else None,
        "worker": worker,
        "event_bus": event_bus_status,
        "event_bus_stuck_processing": event_bus_stuck_processing,
        "task_queue": task_queue_summary,
    })


# ── Serve Vue frontend static files ──
if FRONTEND_DIST.exists():
    app.mount("/assets", StaticFiles(directory=str(FRONTEND_DIST / "assets")), name="assets")
