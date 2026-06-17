from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.exceptions import AppException, ConflictError, ValidationError, PermissionDenied
from app.database import get_db
from app.schemas.common import ApiResponse
from app.middleware.auth import require_permission
from app.models.user import User
from app.services.office.text_editor_service import TextEditorService
from app.services.office.csv_editor_service import CsvEditorService
from app.services.file_share_service import check_file_access

router = APIRouter(prefix="/api/editors", tags=["editors"])

text_svc = TextEditorService()
csv_svc = CsvEditorService()


async def _require_edit_access(db: AsyncSession, file_id: int, user_id: int):
    """Check user has owner or edit share access to the file."""
    from app.models.file import File
    file = await db.get(File, file_id)
    if not file or file.deleted:
        raise AppException("File not found", status_code=404)
    access = await check_file_access(db, file_id, user_id)
    if not access["accessible"]:
        raise PermissionDenied("No permission to access this file")


@router.get("/text/{file_id}")
async def read_text(
    file_id: int,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission("viewer")),
):
    await _require_edit_access(db, file_id, user.id)
    try:
        result = await text_svc.read(db, file_id)
        return ApiResponse(data=result)
    except AppException:
        raise
    except ValueError as e:
        raise ValidationError(str(e))
    except RuntimeError as e:
        raise ConflictError(str(e))


@router.post("/text/{file_id}")
async def save_text(
    file_id: int,
    body: dict,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission("editor")),
):
    await _require_edit_access(db, file_id, user.id)
    try:
        await text_svc.save(db, file_id, body.get("content", ""), body.get("mtime"))
        return ApiResponse(data={"message": "Saved successfully"})
    except AppException:
        raise
    except ValueError as e:
        raise ValidationError(str(e))
    except RuntimeError as e:
        raise ConflictError(str(e))


@router.get("/csv/{file_id}")
async def read_csv(
    file_id: int,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission("viewer")),
):
    await _require_edit_access(db, file_id, user.id)
    try:
        result = await csv_svc.read(db, file_id)
        return ApiResponse(data=result)
    except AppException:
        raise
    except ValueError as e:
        raise ValidationError(str(e))
    except RuntimeError as e:
        raise ConflictError(str(e))


@router.post("/csv/{file_id}")
async def save_csv(
    file_id: int,
    body: dict,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission("editor")),
):
    await _require_edit_access(db, file_id, user.id)
    try:
        await csv_svc.save(db, file_id, body.get("content", ""), body.get("delimiter", ","), body.get("mtime"))
        return ApiResponse(data={"message": "Saved successfully"})
    except AppException:
        raise
    except ValueError as e:
        raise ValidationError(str(e))
    except RuntimeError as e:
        raise ConflictError(str(e))
