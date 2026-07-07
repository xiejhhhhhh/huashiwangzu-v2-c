"""Standalone background task worker process.

This process imports the normal router registry so module task handlers are
registered once, then runs the framework task worker without serving HTTP.
"""
from __future__ import annotations

import asyncio
import logging
import signal

from fastapi import FastAPI
from sqlalchemy import text as sa_text

from app.database import AsyncSessionLocal, dispose_db, engine, init_db
from app.models.system import ensure_framework_scheduling_columns
from app.routers.registry import register_routers
from app.services.module_logger import setup_module_logging, setup_v2_loggers_for_modules
from app.services.private_module_service import set_app_instance
from app.services.task_worker import start_worker, stop_worker, worker_health

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("v2.task_worker_main")


async def _startup() -> None:
    await init_db()
    await ensure_framework_scheduling_columns()
    try:
        async with engine.begin() as conn:
            await conn.execute(sa_text(
                "ALTER TABLE framework_content_packages "
                "ADD COLUMN IF NOT EXISTS origin_type VARCHAR(32) DEFAULT 'uploaded'"
            ))
    except Exception as exc:
        logger.warning("Migration origin_type skipped: %s", exc)

    setup_module_logging()
    app = FastAPI(title="Huashi Wangzu V2 Task Worker")
    set_app_instance(app)
    register_routers(app)
    setup_v2_loggers_for_modules()

    # Touch the DB after module import so startup fails early if credentials drift.
    async with AsyncSessionLocal() as db:
        await db.execute(sa_text("SELECT 1"))

    start_worker()
    logger.info("Standalone task worker started: %s", worker_health())


async def _run_forever() -> None:
    stop_event = asyncio.Event()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, stop_event.set)
        except NotImplementedError:
            pass

    await _startup()
    try:
        await stop_event.wait()
    finally:
        logger.info("Standalone task worker stopping")
        await stop_worker()
        await dispose_db()


def main() -> None:
    asyncio.run(_run_forever())


if __name__ == "__main__":
    main()
