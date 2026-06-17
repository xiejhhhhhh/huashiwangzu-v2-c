import logging
from pathlib import Path
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.responses import ORJSONResponse
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
    yield
    await dispose_db()


app = FastAPI(
    title="Huashi Wangzu V2 API",
    version="2.0.0",
    lifespan=lifespan,
    default_response_class=ORJSONResponse,
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

# Exception handlers
register_exception_handlers(app)

# Routers
register_routers(app)


@app.get("/api/health")
async def health_check():
    from app.database import engine
    from app.schemas.common import ApiResponse

    database_status = "ok"
    try:
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
    except Exception:
        database_status = "unreachable"
    return ApiResponse(data={
        "status": "ok",
        "version": "2.0.0",
        "database": database_status,
    })


# ── Serve Vue frontend static files ──
if FRONTEND_DIST.exists():
    app.mount("/assets", StaticFiles(directory=str(FRONTEND_DIST / "assets")), name="assets")
