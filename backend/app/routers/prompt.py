from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.middleware.auth import require_permission
from app.models.user import User
from app.schemas.common import ApiResponse
from app.services import prompt_service as svc

router = APIRouter(prefix="/api/prompts", tags=["prompts"])


class PromptCategoryCreate(BaseModel):
    name: str
    description: str | None = None
    sort_order: int = 0


class PromptCategoryUpdate(BaseModel):
    name: str | None = None
    description: str | None = None
    sort_order: int | None = None


class PromptTemplateCreate(BaseModel):
    category_id: int | None = None
    name: str
    content: str
    variables: dict | None = None
    description: str | None = None
    is_default: bool = False
    is_enabled: bool = True


class PromptTemplateUpdate(BaseModel):
    category_id: int | None = None
    name: str | None = None
    content: str | None = None
    variables: dict | None = None
    description: str | None = None
    is_default: bool | None = None
    is_enabled: bool | None = None


@router.get("/categories")
async def list_categories(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission("admin")),
):
    return ApiResponse(data=await svc.list_categories(db))


@router.post("/categories")
async def create_category(
    body: PromptCategoryCreate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission("admin")),
):
    return ApiResponse(data=await svc.create_category(db, body.model_dump()))


@router.put("/categories/{category_id}")
async def update_category(
    category_id: int,
    body: PromptCategoryUpdate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission("admin")),
):
    return ApiResponse(data=await svc.update_category(db, category_id, body.model_dump(exclude_none=True)))


@router.delete("/categories/{category_id}")
async def delete_category(
    category_id: int,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission("admin")),
):
    return ApiResponse(data=await svc.delete_category(db, category_id))


@router.get("/templates")
async def list_templates(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission("admin")),
):
    return ApiResponse(data=await svc.list_templates(db))


@router.post("/templates")
async def create_template(
    body: PromptTemplateCreate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission("admin")),
):
    return ApiResponse(data=await svc.create_template(db, body.model_dump()))


@router.put("/templates/{template_id}")
async def update_template(
    template_id: int,
    body: PromptTemplateUpdate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission("admin")),
):
    return ApiResponse(data=await svc.update_template(db, template_id, body.model_dump(exclude_none=True)))


@router.delete("/templates/{template_id}")
async def delete_template(
    template_id: int,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission("admin")),
):
    return ApiResponse(data=await svc.delete_template(db, template_id))
