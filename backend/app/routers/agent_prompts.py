import logging
from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession
from app.database import get_db
from app.schemas.common import ApiResponse
from app.middleware.auth import require_permission
from app.models.user import User
from app.services.agent.prompt_service import prompt_service
from app.core.exceptions import NotFound, ValidationError

logger = logging.getLogger("v2.agent.prompts")

router = APIRouter(prefix="/api/agent", tags=["agent-prompts"])


@router.get("/prompts/categories")
async def list_prompt_categories(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission("viewer")),
):
    cats = await prompt_service.list_categories(db)
    return ApiResponse(data=cats)


@router.post("/prompts/categories")
async def create_prompt_category(
    body: dict,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission("editor")),
):
    name = body.get("name", "")
    if not name:
        raise ValidationError("name is required")
    cat = await prompt_service.create_category(
        db, name, body.get("description"), body.get("sortOrder", 0),
    )
    return ApiResponse(data={"id": cat.id, "name": cat.name})


@router.get("/prompts")
async def list_prompts(
    categoryId: int | None = Query(None),
    page: int = Query(1, ge=1),
    pageSize: int = Query(50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission("viewer")),
):
    data = await prompt_service.list_templates(db, categoryId, page, pageSize)
    return ApiResponse(data=data)


@router.post("/prompts")
async def create_prompt(
    body: dict,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission("editor")),
):
    name = body.get("name", "")
    content = body.get("content", "")
    if not name or not content:
        raise ValidationError("name and content are required")
    t = await prompt_service.create_template(
        db, name=name, content=content,
        category_id=body.get("categoryId"),
        variables=body.get("variables"),
        description=body.get("description"),
        is_default=body.get("isDefault", False),
    )
    return ApiResponse(data={
        "id": t.id, "name": t.name, "isDefault": t.is_default,
    })


@router.get("/prompts/{prompt_id}")
async def get_prompt(
    prompt_id: int,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission("viewer")),
):
    t = await prompt_service.get_template(db, prompt_id)
    return ApiResponse(data={
        "id": t.id, "name": t.name, "content": t.content,
        "categoryId": t.category_id, "variables": t.variables or [],
        "description": t.description, "isDefault": t.is_default,
        "isEnabled": t.is_enabled,
        "createdAt": t.created_at.isoformat() if t.created_at else "",
        "updatedAt": t.updated_at.isoformat() if t.updated_at else "",
    })


@router.put("/prompts/{prompt_id}")
async def update_prompt(
    prompt_id: int,
    body: dict,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission("editor")),
):
    KEY_MAP = {
        "categoryId": "category_id", "isDefault": "is_default", "isEnabled": "is_enabled",
    }
    upd = {}
    for camel_key in ("name", "content", "categoryId", "variables", "description", "isDefault", "isEnabled"):
        if camel_key in body:
            snake_key = KEY_MAP.get(camel_key, camel_key)
            upd[snake_key] = body[camel_key]
    t = await prompt_service.update_template(db, prompt_id, **upd)
    return ApiResponse(data={
        "id": t.id, "name": t.name, "isDefault": t.is_default, "isEnabled": t.is_enabled,
    })


@router.delete("/prompts/{prompt_id}")
async def delete_prompt(
    prompt_id: int,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission("editor")),
):
    await prompt_service.delete_template(db, prompt_id)
    return ApiResponse(data={"message": "Prompt deleted"})


@router.post("/prompts/render")
async def render_prompt(
    body: dict,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission("viewer")),
):
    template_id = body.get("templateId")
    variables = body.get("variables", {})
    content = await prompt_service.render_template(db, template_id, variables)
    return ApiResponse(data={"content": content})


@router.get("/prompts/default")
async def get_default_prompt(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission("viewer")),
):
    t = await prompt_service.get_default_template(db)
    if not t:
        raise NotFound("No default prompt template configured")
    return ApiResponse(data={
        "id": t.id, "name": t.name, "content": t.content,
    })
