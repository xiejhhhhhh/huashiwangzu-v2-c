from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.responses import FileResponse

from app.database import get_db
from app.middleware.auth import require_permission
from app.models.knowledge import Catalog
from app.models.user import User
from app.services.knowledge.vision.page_image_service import (
    ensure_page_image,
    ensure_thumbnail,
)

router = APIRouter(prefix="/api/knowledge/visual", tags=["knowledge-visual"])


async def _get_catalog(db: AsyncSession, catalog_id: int) -> Catalog:
    result = await db.execute(select(Catalog).where(Catalog.id == catalog_id))
    catalog = result.scalar_one_or_none()
    if not catalog:
        raise HTTPException(status_code=404, detail="Knowledge file not found")
    return catalog


def _file_response(path: Path, media_type: str) -> FileResponse:
    return FileResponse(str(path), media_type=media_type, filename=path.name)


@router.get("/page-image/{catalog_id}/{page_num}")
async def get_page_image(
    catalog_id: int,
    page_num: int,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission("viewer")),
) -> FileResponse:
    catalog = await _get_catalog(db, catalog_id)
    path = await ensure_page_image(catalog, page_num)
    if not path:
        raise HTTPException(status_code=404, detail="Page image unavailable")
    return _file_response(path, "image/png")


@router.get("/thumbnail/{catalog_id}/{page_num}")
async def get_thumbnail(
    catalog_id: int,
    page_num: int,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission("viewer")),
) -> FileResponse:
    catalog = await _get_catalog(db, catalog_id)
    path = await ensure_thumbnail(catalog, page_num)
    if not path:
        raise HTTPException(status_code=404, detail="Thumbnail unavailable")
    return _file_response(path, "image/jpeg")
