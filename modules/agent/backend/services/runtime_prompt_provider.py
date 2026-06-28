"""Runtime prompt provider for Agent.

This is the single read path for prompt text used by the Agent runtime. It
loads editable user prompts and read-only system prompts from ``agent_prompts``;
seed text is only a startup fallback when the table is not initialized yet.
"""
from __future__ import annotations

import logging

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models import AgentPrompt
from ..prompt_seeds import PROMPT_SCOPE_SYSTEM, PROMPT_SCOPE_USER, PROMPT_SEED_BY_KEY

logger = logging.getLogger("v2.agent").getChild("runtime_prompt_provider")


class RuntimePromptProvider:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def get_system_prompt(self, key: str) -> str:
        stmt = select(AgentPrompt).where(
            AgentPrompt.key == key,
            AgentPrompt.scope == PROMPT_SCOPE_SYSTEM,
            AgentPrompt.is_active.is_(True),
        ).order_by(AgentPrompt.id.desc()).limit(1)
        result = await self.db.execute(stmt)
        prompt = result.scalar_one_or_none()
        if prompt:
            return prompt.content
        seed = PROMPT_SEED_BY_KEY.get(key)
        if seed:
            logger.warning("Prompt key '%s' missing in DB; using seed fallback", key)
            return seed.content
        logger.warning("Prompt key '%s' missing and has no seed fallback", key)
        return ""

    async def get_user_prompts(
        self,
        owner_id: int,
        category: str | None = None,
    ) -> list[AgentPrompt]:
        stmt = select(AgentPrompt).where(
            AgentPrompt.owner_id == owner_id,
            AgentPrompt.scope == PROMPT_SCOPE_USER,
            AgentPrompt.is_active.is_(True),
            AgentPrompt.status.in_(["published", "active", "draft"]),
        ).order_by(AgentPrompt.id.desc())
        if category:
            stmt = stmt.where(AgentPrompt.category == category)
        result = await self.db.execute(stmt)
        return list(result.scalars().all())

    async def render_system_prompt(self, key: str, variables: dict[str, object] | None = None) -> str:
        return render_template(await self.get_system_prompt(key), variables or {})

    async def render_user_prompt(self, owner_id: int, key: str, variables: dict[str, object] | None = None) -> str:
        stmt = select(AgentPrompt).where(
            AgentPrompt.owner_id == owner_id,
            AgentPrompt.key == key,
            AgentPrompt.scope == PROMPT_SCOPE_USER,
            AgentPrompt.is_active.is_(True),
        ).order_by(AgentPrompt.id.desc()).limit(1)
        result = await self.db.execute(stmt)
        prompt = result.scalar_one_or_none()
        return render_template(prompt.content if prompt else "", variables or {})


async def get_system_prompt(db: AsyncSession, key: str) -> str:
    return await RuntimePromptProvider(db).get_system_prompt(key)


async def render_system_prompt(
    db: AsyncSession,
    key: str,
    variables: dict[str, object] | None = None,
) -> str:
    return await RuntimePromptProvider(db).render_system_prompt(key, variables)


def render_template(template: str, variables: dict[str, object]) -> str:
    text = template or ""
    for name, value in variables.items():
        text = text.replace("{{" + name + "}}", str(value))
    return text
