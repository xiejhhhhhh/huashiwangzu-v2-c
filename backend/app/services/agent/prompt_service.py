import re
import logging
from sqlalchemy import select, func, update
from sqlalchemy.ext.asyncio import AsyncSession
from app.models.prompt import PromptTemplate, PromptCategory
from app.core.exceptions import NotFound, ValidationError

logger = logging.getLogger("v2.agent.prompt")


class PromptService:
    # ── Categories ──

    async def list_categories(self, db: AsyncSession) -> list[dict]:
        r = await db.execute(select(PromptCategory).order_by(PromptCategory.sort_order, PromptCategory.id))
        return [
            {"id": c.id, "name": c.name, "description": c.description, "sortOrder": c.sort_order}
            for c in r.scalars().all()
        ]

    async def create_category(self, db: AsyncSession, name: str, description: str | None = None, sort_order: int = 0) -> PromptCategory:
        cat = PromptCategory(name=name, description=description, sort_order=sort_order)
        db.add(cat)
        await db.commit()
        await db.refresh(cat)
        return cat

    # ── Templates ──

    async def list_templates(
        self, db: AsyncSession, category_id: int | None = None,
        page: int = 1, page_size: int = 50,
    ) -> dict:
        query = select(PromptTemplate)
        if category_id is not None:
            query = query.where(PromptTemplate.category_id == category_id)
        total = await db.scalar(select(func.count()).select_from(query.subquery()))
        query = query.order_by(PromptTemplate.id.desc()).offset((page - 1) * page_size).limit(page_size)
        r = await db.execute(query)
        items = []
        for t in r.scalars().all():
            items.append(self.to_dict(t))
        return {"items": items, "total": total or 0, "page": page, "pageSize": page_size}

    async def get_template(self, db: AsyncSession, template_id: int) -> PromptTemplate:
        t = await db.get(PromptTemplate, template_id)
        if not t:
            raise NotFound(f"PromptTemplate {template_id} not found")
        return t

    async def create_template(
        self, db: AsyncSession, name: str, content: str,
        category_id: int | None = None, variables: list[str] | None = None,
        description: str | None = None, is_default: bool = False,
    ) -> PromptTemplate:
        existing = await db.execute(select(PromptTemplate).where(PromptTemplate.name == name))
        if existing.scalar_one_or_none():
            raise ValidationError(f"Template '{name}' already exists")
        if is_default:
            await self._clear_default_flag(db)
        t = PromptTemplate(
            name=name, content=content, category_id=category_id,
            variables=variables, description=description,
            is_default=is_default, is_enabled=True,
        )
        db.add(t)
        await db.commit()
        await db.refresh(t)
        return t

    async def update_template(
        self, db: AsyncSession, template_id: int, **kwargs,
    ) -> PromptTemplate:
        t = await self.get_template(db, template_id)
        if "name" in kwargs and kwargs["name"] != t.name:
            existing = await db.execute(select(PromptTemplate).where(PromptTemplate.name == kwargs["name"]))
            if existing.scalar_one_or_none():
                raise ValidationError(f"Template name '{kwargs['name']}' already exists")
        if kwargs.get("is_default"):
            await self._clear_default_flag(db)
        for key, value in kwargs.items():
            if hasattr(t, key):
                setattr(t, key, value)
        await db.commit()
        await db.refresh(t)
        return t

    async def delete_template(self, db: AsyncSession, template_id: int) -> bool:
        t = await self.get_template(db, template_id)
        await db.delete(t)
        await db.commit()
        return True

    async def get_default_template(self, db: AsyncSession) -> PromptTemplate | None:
        r = await db.execute(
            select(PromptTemplate).where(PromptTemplate.is_default == True, PromptTemplate.is_enabled == True)
        )
        return r.scalar_one_or_none()

    async def render_template(self, db: AsyncSession, template_id: int, variables: dict[str, str]) -> str:
        t = await self.get_template(db, template_id)
        return self.render_content(t.content, variables)

    def render_content(self, content: str, variables: dict[str, str]) -> str:
        def replacer(m: re.Match) -> str:
            var = m.group(1).strip()
            return variables.get(var, m.group(0))
        return re.sub(r"\{\{(\w+)\}\}", replacer, content)

    async def _clear_default_flag(self, db: AsyncSession):
        await db.execute(
            update(PromptTemplate).where(PromptTemplate.is_default == True).values(is_default=False)
        )

    @staticmethod
    def to_dict(t: PromptTemplate) -> dict:
        return {
            "id": t.id,
            "name": t.name,
            "content": t.content,
            "categoryId": t.category_id,
            "variables": t.variables if t.variables else [],
            "description": t.description,
            "isDefault": t.is_default,
            "isEnabled": t.is_enabled,
            "createdAt": t.created_at.isoformat() if t.created_at else "",
            "updatedAt": t.updated_at.isoformat() if t.updated_at else "",
        }


prompt_service = PromptService()
