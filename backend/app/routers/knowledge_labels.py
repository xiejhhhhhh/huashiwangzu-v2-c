from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.middleware.auth import require_permission
from app.models.user import User
from app.schemas.common import ApiResponse
from app.services.knowledge.label.label_service import LabelService

router = APIRouter(prefix="/api/knowledge/labels", tags=["knowledge-labels"])


def _label_dict(label) -> dict:
    return {
        "id": label.id, "targetType": label.target_type,
        "targetId": label.target_id, "label": label.label,
        "category": label.label_category,
        "passedAdmission": label.passed_admission,
    }


@router.get("/search")
async def search_labels(
    target_type: str | None = None,
    target_id: int | None = None,
    only_admitted: bool = Query(False),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission("viewer")),
):
    labels = await LabelService.get_labels(db, target_type, target_id, only_admitted)
    return ApiResponse(data={"items": [_label_dict(label) for label in labels]})


@router.get("/files/{catalog_id}")
async def file_labels(
    catalog_id: int,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission("viewer")),
):
    labels = await LabelService.get_labels_by_target(db, "file", catalog_id)
    return ApiResponse(data={"items": [_label_dict(label) for label in labels]})


@router.post("/index/{catalog_id}")
async def index_file_labels(
    catalog_id: int,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission("editor")),
):
    result = await LabelService.index_file_labels(db, catalog_id)
    return ApiResponse(data=result)
