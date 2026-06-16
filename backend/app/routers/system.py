from fastapi import APIRouter, Depends
from sqlalchemy import select, func, desc
from sqlalchemy.ext.asyncio import AsyncSession
from app.database import get_db
from app.schemas.common import ApiResponse
from app.schemas.system import *
from app.middleware.auth import require_permission
from app.models.user import User
from app.services import system_service as svc, knowledge_service
from app.core.exceptions import NotFound

router = APIRouter(tags=["system-old"])

# ── Dashboard (kept for backward compat, main routes now in dashboard.py) ──
@router.get("/api/dashboard/stats")
async def dashboard_stats(db: AsyncSession = Depends(get_db), user: User = Depends(require_permission("viewer"))):
    return ApiResponse(data=await svc.get_dashboard_stats(db))



# ── My Personal Tasks (moved from /api/tasks to /api/my-tasks) ──
@router.get("/api/my-tasks")
async def get_my_tasks(db: AsyncSession = Depends(get_db), user: User = Depends(require_permission("viewer"))):
    items = await svc.get_tasks(db, user.id)
    return ApiResponse(data=[TaskResponse.model_validate(i) for i in items])

# ── Knowledge / Catalog ──
@router.get("/api/knowledge/catalogs")
async def list_catalogs(db: AsyncSession = Depends(get_db), user: User = Depends(require_permission("viewer"))):
    from app.models.knowledge import Catalog
    r = await db.execute(select(Catalog).order_by(desc(Catalog.id)))
    return ApiResponse(data=[CatalogResponse.model_validate(c) for c in r.scalars().all()])

@router.post("/api/knowledge/search")
async def search_knowledge(body: dict, db: AsyncSession = Depends(get_db),
                           user: User = Depends(require_permission("viewer"))):
    results = await knowledge_service.hybrid_search(db, body.get("query", ""), body.get("top_k", 10))
    return ApiResponse(data=results)

# ── File Preview ──
import os
@router.get("/api/desktop/file-preview/{file_id}")
async def file_preview(file_id: int, db: AsyncSession = Depends(get_db),
                       user: User = Depends(require_permission("viewer"))):
    from app.models.file import File as FileModel
    f = await db.get(FileModel, file_id)
    if not f: raise NotFound("File not found")
    return ApiResponse(data={"id": f.id, "name": f"{f.name}.{f.extension}", "size": f.size, "mime_type": f.mime_type})
