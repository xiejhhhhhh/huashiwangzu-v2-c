import logging
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ConflictError, NotFound
from app.models.prompt import PromptCategory, PromptTemplate

logger = logging.getLogger("v2.prompt")


def _category_to_dict(category: PromptCategory) -> dict:
    return {
        "id": category.id,
        "name": category.name,
        "description": category.description,
        "sort_order": category.sort_order,
        "created_at": category.created_at.isoformat() if category.created_at else None,
        "updated_at": category.updated_at.isoformat() if category.updated_at else None,
    }


def _template_to_dict(template: PromptTemplate) -> dict:
    return {
        "id": template.id,
        "category_id": template.category_id,
        "name": template.name,
        "content": template.content,
        "variables": template.variables,
        "description": template.description,
        "is_default": template.is_default,
        "is_enabled": template.is_enabled,
        "created_at": template.created_at.isoformat() if template.created_at else None,
        "updated_at": template.updated_at.isoformat() if template.updated_at else None,
    }


async def list_categories(db: AsyncSession) -> list[dict]:
    result = await db.execute(select(PromptCategory).order_by(PromptCategory.sort_order, PromptCategory.id))
    return [_category_to_dict(item) for item in result.scalars().all()]


async def get_category(db: AsyncSession, category_id: int) -> dict:
    category = await db.get(PromptCategory, category_id)
    if not category:
        raise NotFound(f"Prompt category '{category_id}' not found")
    return _category_to_dict(category)


async def create_category(db: AsyncSession, data: dict) -> dict:
    existing = await db.execute(select(PromptCategory).where(PromptCategory.name == data["name"]))
    if existing.scalar_one_or_none():
        raise ConflictError(f"Prompt category '{data['name']}' already exists")
    category = PromptCategory(
        name=data["name"],
        description=data.get("description"),
        sort_order=data.get("sort_order", 0),
    )
    db.add(category)
    await db.commit()
    await db.refresh(category)
    return _category_to_dict(category)


async def update_category(db: AsyncSession, category_id: int, data: dict) -> dict:
    category = await db.get(PromptCategory, category_id)
    if not category:
        raise NotFound(f"Prompt category '{category_id}' not found")
    if "name" in data and data["name"] and data["name"] != category.name:
        existing = await db.execute(select(PromptCategory).where(PromptCategory.name == data["name"]))
        if existing.scalar_one_or_none():
            raise ConflictError(f"Prompt category '{data['name']}' already exists")
        category.name = data["name"]
    if "description" in data:
        category.description = data["description"]
    if "sort_order" in data and data["sort_order"] is not None:
        category.sort_order = data["sort_order"]
    await db.commit()
    await db.refresh(category)
    return _category_to_dict(category)


async def delete_category(db: AsyncSession, category_id: int) -> dict:
    category = await db.get(PromptCategory, category_id)
    if not category:
        raise NotFound(f"Prompt category '{category_id}' not found")
    await db.delete(category)
    await db.commit()
    return {"ok": True}


async def list_templates(db: AsyncSession) -> list[dict]:
    result = await db.execute(select(PromptTemplate).order_by(PromptTemplate.id))
    return [_template_to_dict(item) for item in result.scalars().all()]


async def get_template(db: AsyncSession, template_id: int) -> dict:
    template = await db.get(PromptTemplate, template_id)
    if not template:
        raise NotFound(f"Prompt template '{template_id}' not found")
    return _template_to_dict(template)


async def create_template(db: AsyncSession, data: dict) -> dict:
    existing = await db.execute(select(PromptTemplate).where(PromptTemplate.name == data["name"]))
    if existing.scalar_one_or_none():
        raise ConflictError(f"Prompt template '{data['name']}' already exists")
    template = PromptTemplate(
        category_id=data.get("category_id"),
        name=data["name"],
        content=data["content"],
        variables=data.get("variables"),
        description=data.get("description"),
        is_default=data.get("is_default", False),
        is_enabled=data.get("is_enabled", True),
    )
    db.add(template)
    await db.commit()
    await db.refresh(template)
    return _template_to_dict(template)


async def update_template(db: AsyncSession, template_id: int, data: dict) -> dict:
    template = await db.get(PromptTemplate, template_id)
    if not template:
        raise NotFound(f"Prompt template '{template_id}' not found")
    if "name" in data and data["name"] and data["name"] != template.name:
        existing = await db.execute(select(PromptTemplate).where(PromptTemplate.name == data["name"]))
        if existing.scalar_one_or_none():
            raise ConflictError(f"Prompt template '{data['name']}' already exists")
        template.name = data["name"]
    if "category_id" in data:
        template.category_id = data["category_id"]
    if "content" in data:
        template.content = data["content"]
    if "variables" in data:
        template.variables = data["variables"]
    if "description" in data:
        template.description = data["description"]
    if "is_default" in data and data["is_default"] is not None:
        template.is_default = data["is_default"]
    if "is_enabled" in data and data["is_enabled"] is not None:
        template.is_enabled = data["is_enabled"]
    await db.commit()
    await db.refresh(template)
    return _template_to_dict(template)


async def delete_template(db: AsyncSession, template_id: int) -> dict:
    template = await db.get(PromptTemplate, template_id)
    if not template:
        raise NotFound(f"Prompt template '{template_id}' not found")
    await db.delete(template)
    await db.commit()
    return {"ok": True}
