from sqlalchemy.ext.asyncio import AsyncSession
from app.models.prompt import PromptCategory
from app.services.agent.prompt_service import prompt_service
from app.core.exceptions import NotFound, ValidationError


async def update_category(db: AsyncSession, category_id: int, data: dict) -> PromptCategory:
    cat = await db.get(PromptCategory, category_id)
    if not cat:
        raise NotFound(f"PromptCategory {category_id} not found")
    if "name" in data and not data["name"]:
        raise ValidationError("name is required")
    if "name" in data:
        cat.name = data["name"]
    if "description" in data:
        cat.description = data["description"]
    if "sortOrder" in data:
        cat.sort_order = data["sortOrder"]
    await db.commit()
    await db.refresh(cat)
    return cat


async def delete_category(db: AsyncSession, category_id: int) -> bool:
    cat = await db.get(PromptCategory, category_id)
    if not cat:
        raise NotFound(f"PromptCategory {category_id} not found")
    await db.delete(cat)
    await db.commit()
    return True


async def copy_template(db: AsyncSession, template_id: int, name: str | None = None):
    template = await prompt_service.get_template(db, template_id)
    copy_name = name or f"{template.name} 副本"
    return await prompt_service.create_template(
        db, name=copy_name, content=template.content, category_id=template.category_id,
        variables=template.variables, description=template.description, is_default=False,
    )
