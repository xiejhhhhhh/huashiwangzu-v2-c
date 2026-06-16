from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from app.database import get_db
from app.schemas.common import ApiResponse
from app.services.system_status_service import get_system_status

router = APIRouter(prefix="/api/system", tags=["system-status"])


@router.get("/status")
async def system_status(db: AsyncSession = Depends(get_db)):
    data = await get_system_status(db)
    return ApiResponse(data=data)
