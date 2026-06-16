from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.middleware.auth import require_permission
from app.models.user import User
from app.schemas.common import ApiResponse
from app.services.knowledge.evaluation import service

router = APIRouter(prefix="/api/knowledge/evaluation", tags=["knowledge-evaluation"])


@router.get("/overview")
async def get_overview(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission("viewer")),
):
    return ApiResponse(data=await service.overview(db))


@router.get("/history")
async def get_history(
    limit: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission("viewer")),
):
    return ApiResponse(data=await service.history(db, limit=limit))


@router.get("/records/{record_id}")
async def get_record(
    record_id: int,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission("viewer")),
):
    data = await service.detail(db, record_id)
    if not data:
        raise HTTPException(status_code=404, detail="Evaluation record not found")
    return ApiResponse(data=data)


@router.post("/run")
async def run_evaluation(
    top_k: int = Query(10, ge=1, le=30),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission("editor")),
):
    return ApiResponse(data=await service.run_evaluation(db, top_k=top_k))
