import logging
from pathlib import Path
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.responses import ORJSONResponse

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s %(message)s",
    datefmt="%H:%M:%S",
)
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.responses import FileResponse
from app.config import get_settings
from app.database import init_db, dispose_db
from app.core.handlers import register_exception_handlers
from app.routers import auth, desktop, files, file_transfer, recycle, users, roles, system, logs, system_status, dashboard, settings, backup, tasks, office, office_export, editors, notifications, feedback, app_manager, agent_session, agent_tools, agent_prompts, agent_prompt_actions, health, image_vision, knowledge, knowledge_aggregation, knowledge_analysis_results, knowledge_entity_merge, knowledge_dictionary, knowledge_evaluation, knowledge_evidence_write, knowledge_governance, knowledge_governance_write, knowledge_graph, knowledge_labels, knowledge_tasks, knowledge_visual_resources, menu

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

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=config.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Exception handlers
register_exception_handlers(app)

# Routers
app.include_router(auth.router)
app.include_router(desktop.router)
app.include_router(files.router)
app.include_router(file_transfer.router)
app.include_router(recycle.router)
app.include_router(users.router)
app.include_router(roles.router)
app.include_router(system.router)
app.include_router(logs.router)
app.include_router(system_status.router)
app.include_router(dashboard.router)
app.include_router(settings.router)
app.include_router(backup.router)
app.include_router(tasks.router)
app.include_router(notifications.router)
app.include_router(feedback.router)
app.include_router(office.router)
app.include_router(office_export.router)
app.include_router(editors.router)
app.include_router(app_manager.router)
app.include_router(menu.router)
app.include_router(agent_session.router)
app.include_router(agent_tools.router)
app.include_router(agent_prompts.router)
app.include_router(agent_prompt_actions.router)
app.include_router(health.router)
app.include_router(image_vision.router)
app.include_router(knowledge.router)
app.include_router(knowledge_aggregation.router)
app.include_router(knowledge_analysis_results.router)
app.include_router(knowledge_entity_merge.router)
app.include_router(knowledge_dictionary.router)
app.include_router(knowledge_evaluation.router)
app.include_router(knowledge_evidence_write.router)
app.include_router(knowledge_governance.router)
app.include_router(knowledge_governance_write.router)
app.include_router(knowledge_graph.router)
app.include_router(knowledge_labels.router)
app.include_router(knowledge_tasks.router)
app.include_router(knowledge_visual_resources.router)


@app.get("/api/health")
async def health_check():
    from app.schemas.common import ApiResponse
    return ApiResponse(data={"status": "ok", "version": "2.0.0"})


# ── Serve Vue frontend static files ──
if FRONTEND_DIST.exists():
    app.mount("/assets", StaticFiles(directory=str(FRONTEND_DIST / "assets")), name="assets")

    @app.exception_handler(StarletteHTTPException)
    async def spa_fallback(request, exc):
        # API 路径的 404 直接返回 404，不走 SPA 兜底
        if request.url.path.startswith("/api"):
            return ORJSONResponse(
                status_code=exc.status_code,
                content={"success": False, "data": None, "error": exc.detail or "Not found", "errors": None},
            )
        # 非 API 路径的 404 返回 SPA index.html
        if exc.status_code == 404:
            return FileResponse(str(FRONTEND_DIST / "index.html"))
        raise exc

    # Serve static files from dist (assets, favicon, etc.)
    @app.get("/assets/{path:path}")
    async def serve_assets(path: str):
        file_path = FRONTEND_DIST / "assets" / path
        if file_path.exists():
            return FileResponse(str(file_path))
        raise StarletteHTTPException(status_code=404)
