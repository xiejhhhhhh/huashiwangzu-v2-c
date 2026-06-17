from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from app.database import get_db
from app.schemas.common import ApiResponse
from app.middleware.auth import require_permission
from app.models.user import User
from app.services import file_create_service
from app.services.system_service import create_log
from pydantic import BaseModel

router = APIRouter(prefix="/api/files", tags=["files"])


class CreateFileRequest(BaseModel):
    name: str
    extension: str
    folder_id: int | None = None


@router.post("/create-file")
async def create_file(
    body: CreateFileRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission("editor")),
):
    result = await file_create_service.create_file(
        db, body.name, body.extension, user.id, body.folder_id,
    )
    await create_log(db, "info", "file_system", "create_file",
                     f"Created {body.extension} file '{result['name']}' id={result['id']}", user_id=user.id)
    return ApiResponse(data=result)
