from fastapi import APIRouter, Depends, Path
from sqlalchemy.ext.asyncio import AsyncSession
from app.database import get_db
from app.schemas.common import ApiResponse
from app.services.system_status_service import get_system_status
from app.services.trace_store import get_trace_tree
from app.core.exceptions import NotFound

router = APIRouter(prefix="/api/system", tags=["system-status"])


@router.get("/status")
async def system_status(db: AsyncSession = Depends(get_db)):
    data = await get_system_status(db)
    return ApiResponse(data=data)


@router.get("/trace/{trace_id}")
async def get_trace(trace_id: str = Path(...)):
    tree = await get_trace_tree(trace_id)
    if not tree:
        raise NotFound(f"Trace '{trace_id}' not found")
    return ApiResponse(data={
        "trace_id": trace_id,
        "spans": tree,
    })
