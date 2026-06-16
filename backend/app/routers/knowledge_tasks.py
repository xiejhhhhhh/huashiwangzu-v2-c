import asyncio

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import NotFound
from app.database import AsyncSessionLocal, get_db
from app.middleware.auth import require_permission
from app.models.knowledge import Catalog, KnowledgeTask
from app.models.file import File
from app.models.user import User
from app.schemas.common import ApiResponse
from app.schemas.knowledge import RerunRequest, TriggerRequest
from app.services.knowledge.catalog_service import CatalogService
from app.services.knowledge.pipeline import PIPELINE_ORDER, create_next_task, create_pipeline_tasks
from app.services.knowledge.task_snapshot import build_task_snapshot, sse_payload

router = APIRouter(prefix="/api/knowledge/tasks", tags=["knowledge-tasks"])


@router.post("/trigger")
async def trigger_analysis(body: TriggerRequest, db: AsyncSession = Depends(get_db), user: User = Depends(require_permission("editor"))):
    file_path = body.file_path
    if not file_path and body.file_id:
        file = await db.get(File, body.file_id)
        if not file:
            raise HTTPException(status_code=404, detail="File not found")
        file_path = file.storage_path
    if not file_path:
        raise HTTPException(status_code=422, detail="Provide file_path or file_id")
    catalog, is_new = await CatalogService.create_or_get(db, file_path, owner_id=body.owner_id or user.id)
    if not is_new:
        return ApiResponse(data={"catalog_id": catalog.id, "status": catalog.status, "message": "File already exists"})
    await create_pipeline_tasks(db, catalog.id)
    return ApiResponse(data={"catalog_id": catalog.id, "status": "queued", "message": "Pipeline tasks created"})


@router.get("/snapshot")
async def task_snapshot(db: AsyncSession = Depends(get_db), user: User = Depends(require_permission("viewer"))):
    return ApiResponse(data=await build_task_snapshot(db))


@router.get("/stream")
async def task_stream(user: User = Depends(require_permission("viewer"))):
    async def generate():
        while True:
            async with AsyncSessionLocal() as db:
                yield sse_payload(await build_task_snapshot(db))
            await asyncio.sleep(2)
    return StreamingResponse(generate(), media_type="text/event-stream")


@router.get("/{catalog_id}")
async def get_task_progress(catalog_id: int, db: AsyncSession = Depends(get_db), user: User = Depends(require_permission("viewer"))):
    result = await db.execute(select(KnowledgeTask).where(KnowledgeTask.catalog_id == catalog_id).order_by(KnowledgeTask.id))
    tasks = result.scalars().all()
    catalog = await db.get(Catalog, catalog_id)
    if not catalog:
        raise NotFound(f"Catalog {catalog_id} not found")
    return ApiResponse(data={"catalog_id": catalog_id, "catalog_status": catalog.status, "tasks": [
        {"id": t.id, "task_type": t.task_type, "status": t.status, "progress": t.progress, "error": t.error}
        for t in tasks
    ]})


@router.post("/rerun/{catalog_id}")
async def rerun_layer(catalog_id: int, body: RerunRequest, db: AsyncSession = Depends(get_db), user: User = Depends(require_permission("editor"))):
    if body.layer not in PIPELINE_ORDER:
        return ApiResponse(success=False, error=f"Invalid layer '{body.layer}'", data=None)
    catalog = await db.get(Catalog, catalog_id)
    if not catalog:
        raise NotFound(f"Catalog {catalog_id} not found")
    existing = await db.execute(select(KnowledgeTask).where(
        KnowledgeTask.catalog_id == catalog_id,
        KnowledgeTask.task_type == body.layer,
        KnowledgeTask.status.in_(["pending", "processing"]),
    ))
    if existing.scalar_one_or_none():
        return ApiResponse(data={"catalog_id": catalog_id, "layer": body.layer, "status": "already_queued"})
    await create_next_task(db, catalog_id, body.layer)
    catalog.status = "pending"
    await db.commit()
    return ApiResponse(data={"catalog_id": catalog_id, "layer": body.layer, "status": "queued"})
