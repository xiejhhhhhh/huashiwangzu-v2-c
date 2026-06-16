from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from app.database import get_db
from app.schemas.common import ApiResponse
from app.middleware.auth import require_permission
from app.models.user import User
from app.services.agent.prompt_service import prompt_service
from app.services.agent.prompt_admin_service import update_category, delete_category, copy_template
from app.core.exceptions import ValidationError

router = APIRouter(prefix="/api/agent/prompts", tags=["agent-prompt-actions"])


@router.put("/categories/{category_id}")
async def update_prompt_category(
    category_id: int,
    body: dict,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("editor")),
):
    category = await update_category(db, category_id, body)
    return ApiResponse(data={
        "id": category.id,
        "name": category.name,
        "description": category.description,
        "sortOrder": category.sort_order,
    })


@router.delete("/categories/{category_id}")
async def delete_prompt_category(
    category_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("admin")),
):
    await delete_category(db, category_id)
    return ApiResponse(data={"message": "Category deleted"})


@router.post("/{prompt_id}/toggle-enabled")
async def toggle_prompt_enabled(
    prompt_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("editor")),
):
    template = await prompt_service.get_template(db, prompt_id)
    updated = await prompt_service.update_template(
        db, prompt_id, is_enabled=not template.is_enabled
    )
    return ApiResponse(data=prompt_service.to_dict(updated))


@router.post("/{prompt_id}/copy")
async def copy_prompt(
    prompt_id: int,
    body: dict | None = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("editor")),
):
    template = await copy_template(db, prompt_id, (body or {}).get("name"))
    return ApiResponse(data=prompt_service.to_dict(template))


@router.post("/{prompt_id}/set-default")
async def set_default_prompt(
    prompt_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("editor")),
):
    template = await prompt_service.get_template(db, prompt_id)
    if not template.is_enabled:
        raise ValidationError("Disabled prompt cannot be default")
    updated = await prompt_service.update_template(db, prompt_id, is_default=True)
    return ApiResponse(data=prompt_service.to_dict(updated))
