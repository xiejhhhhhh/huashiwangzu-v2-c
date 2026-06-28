import sys
from pathlib import Path

import pytest

REPO_DIR = Path(__file__).resolve().parents[3]
if str(REPO_DIR) not in sys.path:
    sys.path.insert(0, str(REPO_DIR))

from app.core.exceptions import NotFound, PermissionDenied
from modules.agent.backend.models_prompt import AgentPrompt
from modules.agent.backend.prompt_seeds import (
    COMPRESSION_SUMMARY_KEY,
    PROMPT_SCOPE_SYSTEM,
    PROMPT_SCOPE_USER,
    PROMPT_SEED_BY_KEY,
)
from modules.agent.backend.services.prompt_service import delete_prompt, update_prompt
from modules.agent.backend.services.runtime_prompt_provider import RuntimePromptProvider, render_template


def test_render_template_replaces_variables():
    assert render_template("hello {{name}}", {"name": "agent"}) == "hello agent"


@pytest.mark.asyncio
async def test_runtime_provider_falls_back_to_seed_when_db_missing(monkeypatch):
    class EmptyResult:
        def scalar_one_or_none(self):
            return None

    class EmptyDb:
        async def execute(self, stmt):
            return EmptyResult()

    provider = RuntimePromptProvider(EmptyDb())
    text = await provider.get_system_prompt(COMPRESSION_SUMMARY_KEY)
    assert PROMPT_SEED_BY_KEY[COMPRESSION_SUMMARY_KEY].content == text


@pytest.mark.asyncio
async def test_system_prompt_is_read_only_for_service(monkeypatch):
    prompt = AgentPrompt(
        owner_id=None,
        key=COMPRESSION_SUMMARY_KEY,
        title="system",
        category="runtime",
        content="content",
        scope=PROMPT_SCOPE_SYSTEM,
        is_read_only=True,
        is_active=True,
        status="published",
    )
    prompt.id = 1

    class Db:
        async def get(self, model, prompt_id):
            return prompt

    with pytest.raises(PermissionDenied):
        await update_prompt(Db(), owner_id=1, prompt_id=1, data={"content": "new"})
    with pytest.raises(PermissionDenied):
        await delete_prompt(Db(), owner_id=1, prompt_id=1)


@pytest.mark.asyncio
async def test_user_cannot_update_another_users_prompt():
    prompt = AgentPrompt(
        owner_id=2,
        key="",
        title="user",
        category="custom",
        content="content",
        scope=PROMPT_SCOPE_USER,
        is_read_only=False,
        is_active=True,
        status="draft",
    )
    prompt.id = 9

    class Db:
        async def get(self, model, prompt_id):
            return prompt

    with pytest.raises(NotFound):
        await update_prompt(Db(), owner_id=1, prompt_id=9, data={"content": "new"})
