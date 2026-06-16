from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.schemas.common import ApiResponse
from app.services.system_status_service import get_system_status

router = APIRouter(prefix="/api/health", tags=["health"])


@router.get("/deep")
async def deep_health(db: AsyncSession = Depends(get_db)):
    data = await get_system_status(db)
    checks = [value.get("status", False) for value in data.values() if isinstance(value, dict)]
    return ApiResponse(data={"ready": all(checks), "checks": data})
