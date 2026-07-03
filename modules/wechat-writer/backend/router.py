"""FastAPI router for wechat-writer module."""

import logging

from app.middleware.auth import require_permission
from app.models.user import User
from app.schemas.common import ApiResponse
from app.services.file_reader import resolve_caller_user_id as resolve_user_id
from app.services.module_registry import register_capability
from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel

from .init_db import _run_startup_init
from .services import (
    create_draft,
    delete_draft,
    delete_prompt,
    generate_article,
    generate_outline,
    generate_topics,
    get_draft,
    list_drafts,
    list_prompts,
    save_prompt,
    update_draft,
    validate_content,
)

logger = logging.getLogger("v2.wechat_writer").getChild("router")
router = APIRouter(prefix="/api/wechat-writer", tags=["wechat-writer"])

_run_startup_init()


# ── Request/Response models ─────────────────────────────────────

class TopicsRequest(BaseModel):
    direction: str

class OutlineRequest(BaseModel):
    topic: str
    direction: str = ""

class ArticleRequest(BaseModel):
    topic: str
    outline: str
    direction: str = ""

class ValidateRequest(BaseModel):
    content: str

class DraftCreateRequest(BaseModel):
    title: str = ""
    outline: dict | None = None
    content: str = ""
    article_type: str = ""
    keywords: list | None = None
    notes: str = ""
    status: str = "draft"

class DraftUpdateRequest(BaseModel):
    title: str | None = None
    outline: dict | None = None
    content: str | None = None
    article_type: str | None = None
    keywords: list | None = None
    notes: str | None = None
    status: str | None = None

class PromptSaveRequest(BaseModel):
    key: str
    name: str = ""
    content: str
    description: str = ""
    category: str = "custom"


# ── Generation endpoints ────────────────────────────────────────

@router.post("/topics")
async def api_generate_topics(
    payload: TopicsRequest,
    user: User = Depends(require_permission("editor")),
):
    result = await generate_topics(payload.direction, user.id)
    return ApiResponse(data=result)


@router.post("/outline")
async def api_generate_outline(
    payload: OutlineRequest,
    user: User = Depends(require_permission("editor")),
):
    result = await generate_outline(payload.topic, payload.direction, user.id)
    return ApiResponse(data=result)


@router.post("/article")
async def api_generate_article(
    payload: ArticleRequest,
    user: User = Depends(require_permission("editor")),
):
    result = await generate_article(payload.topic, payload.outline, payload.direction, user.id)
    return ApiResponse(data=result)


@router.post("/validate")
async def api_validate_content(
    payload: ValidateRequest,
    user: User = Depends(require_permission("editor")),
):
    result = await validate_content(payload.content, user.id)
    return ApiResponse(data=result)


# ── Draft CRUD endpoints ────────────────────────────────────────

@router.get("/drafts")
async def api_list_drafts(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    user: User = Depends(require_permission("viewer")),
):
    result = await list_drafts(user.id, page, page_size)
    return ApiResponse(data=result)


@router.get("/drafts/{draft_id}")
async def api_get_draft(
    draft_id: int,
    user: User = Depends(require_permission("viewer")),
):
    result = await get_draft(draft_id, user.id)
    if not result:
        from app.core.exceptions import NotFound
        raise NotFound("Draft not found")
    return ApiResponse(data=result)


@router.post("/drafts")
async def api_create_draft(
    payload: DraftCreateRequest,
    user: User = Depends(require_permission("editor")),
):
    result = await create_draft(payload.model_dump(exclude_none=True), user.id)
    return ApiResponse(data=result)


@router.put("/drafts/{draft_id}")
async def api_update_draft(
    draft_id: int,
    payload: DraftUpdateRequest,
    user: User = Depends(require_permission("editor")),
):
    result = await update_draft(draft_id, payload.model_dump(exclude_none=True), user.id)
    if not result:
        from app.core.exceptions import NotFound
        raise NotFound("Draft not found")
    return ApiResponse(data=result)


@router.delete("/drafts/{draft_id}")
async def api_delete_draft(
    draft_id: int,
    user: User = Depends(require_permission("editor")),
):
    ok = await delete_draft(draft_id, user.id)
    if not ok:
        from app.core.exceptions import NotFound
        raise NotFound("Draft not found")
    return ApiResponse(data={"deleted": True})


# ── Prompt CRUD endpoints ───────────────────────────────────────

@router.get("/prompts")
async def api_list_prompts(
    category: str | None = Query(default=None),
    user: User = Depends(require_permission("viewer")),
):
    result = await list_prompts(user.id, category)
    return ApiResponse(data=result)


@router.post("/prompts")
async def api_save_prompt(
    payload: PromptSaveRequest,
    user: User = Depends(require_permission("admin")),
):
    result = await save_prompt(payload.model_dump(), user.id)
    return ApiResponse(data=result)


@router.delete("/prompts/{prompt_id}")
async def api_delete_prompt(
    prompt_id: int,
    user: User = Depends(require_permission("admin")),
):
    ok = await delete_prompt(prompt_id, user.id)
    if not ok:
        from app.core.exceptions import NotFound
        raise NotFound("Prompt not found")
    return ApiResponse(data={"deleted": True})


# ── Cross-module capabilities ───────────────────────────────────

async def _cap_generate_topics(params: dict, caller: str) -> dict:
    owner_id = resolve_user_id(caller)
    direction = str(params.get("direction", "") or "")
    return await generate_topics(direction, owner_id)


async def _cap_generate_outline(params: dict, caller: str) -> dict:
    owner_id = resolve_user_id(caller)
    topic = str(params.get("topic", "") or "")
    direction = str(params.get("direction", "") or "")
    return await generate_outline(topic, direction, owner_id)


async def _cap_generate_article(params: dict, caller: str) -> dict:
    owner_id = resolve_user_id(caller)
    topic = str(params.get("topic", "") or "")
    outline = str(params.get("outline", "") or "")
    direction = str(params.get("direction", "") or "")
    return await generate_article(topic, outline, direction, owner_id)


async def _cap_validate_content(params: dict, caller: str) -> dict:
    owner_id = resolve_user_id(caller)
    content = str(params.get("content", "") or "")
    return await validate_content(content, owner_id)


register_capability(
    "wechat-writer", "generate_topics", _cap_generate_topics,
    description="根据产品/季节/问题肌主题生成公众号选题建议",
    brief="生成选题",
    parameters={"direction": {"type": "string", "description": "创作方向描述"}},
    min_role="editor",
)
register_capability(
    "wechat-writer", "generate_outline", _cap_generate_outline,
    description="根据选题生成公众号文章大纲",
    brief="生成大纲",
    parameters={
        "topic": {"type": "string", "description": "选题标题"},
        "direction": {"type": "string", "description": "创作方向"},
    },
    min_role="editor",
)
register_capability(
    "wechat-writer", "generate_article", _cap_generate_article,
    description="根据大纲生成完整公众号文章初稿",
    brief="生成文章",
    parameters={
        "topic": {"type": "string", "description": "选题标题"},
        "outline": {"type": "string", "description": "大纲文本"},
        "direction": {"type": "string", "description": "创作方向"},
    },
    min_role="editor",
)
register_capability(
    "wechat-writer", "validate_content", _cap_validate_content,
    description="校验成分/功效内容的专业性，结合知识库搜索",
    brief="内容校验",
    parameters={"content": {"type": "string", "description": "需要校验的文本"}},
    min_role="editor",
)
