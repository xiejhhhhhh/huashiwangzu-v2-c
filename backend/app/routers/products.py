"""Product Catalog HTTP —— GET /api/desktop/products。

Gate4：只返回 Product，不返回 Parser/Provider/Service/Viewer/Editor。
"""
from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import NotFound
from app.database import get_db
from app.middleware.auth import require_permission
from app.models.user import User
from app.schemas.common import ApiResponse
from app.services.product_catalog_service import get_effective_product, list_effective_products

router = APIRouter(prefix="/api/desktop", tags=["desktop-products"])


@router.get("/products")
async def list_products(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("viewer")),
):
    catalog = await list_effective_products(db, current_user)
    return ApiResponse(data=catalog)


@router.get("/products/{product_id}")
async def get_product(
    product_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("viewer")),
):
    product = await get_effective_product(db, current_user, product_id)
    if product is None:
        raise NotFound("Product not found")
    return ApiResponse(data=product)
