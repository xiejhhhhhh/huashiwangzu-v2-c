"""FastAPI router for douyin-delivery module."""

import logging

from app.middleware.auth import require_permission
from app.models.user import User
from app.schemas.common import ApiResponse
from app.services.file_reader import resolve_caller_user_id as resolve_user_id
from app.services.module_registry import register_capability
from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel

from .delivery_services import (
    cleanup_marked_data,
    create_account,
    create_delivery_task,
    create_material,
    delete_account,
    delete_delivery_task,
    delete_material,
    list_accounts,
    list_delivery_tasks,
    list_materials,
    mark_delivery_task_status,
    update_account,
    update_delivery_task,
    update_material,
)
from .init_db import _run_startup_init
from .services import (
    analyze_campaign,
    create_campaign,
    create_product,
    delete_ad_copy,
    delete_campaign,
    delete_product,
    delete_prompt,
    delete_script,
    generate_ad_copy,
    generate_script,
    get_script,
    list_ad_copies,
    list_campaigns,
    list_products,
    list_prompts,
    list_scripts,
    save_ad_copy,
    save_prompt,
    save_script,
    update_ad_copy,
    update_campaign,
    update_product,
    update_script,
    validate_content,
)

logger = logging.getLogger("v2.douyin_delivery").getChild("router")
router = APIRouter(prefix="/api/douyin-delivery", tags=["douyin-delivery"])

_run_startup_init()


# ── Request/Response models ─────────────────────────────────────

class ScriptGenerateRequest(BaseModel):
    product: str
    channel: str = "local_push"

class AdCopyGenerateRequest(BaseModel):
    product: str
    channel: str = "ocean_engine"
    ad_type: str = "feed"

class ValidateRequest(BaseModel):
    content: str

class ProductCreateRequest(BaseModel):
    name: str
    category: str = ""
    selling_points: list | None = None
    ingredients: list | None = None
    target_audience: str = ""
    brand: str = "俏小喵"
    notes: str = ""

class ProductUpdateRequest(BaseModel):
    name: str | None = None
    category: str | None = None
    selling_points: list | None = None
    ingredients: list | None = None
    target_audience: str | None = None
    brand: str | None = None
    notes: str | None = None

class ScriptSaveRequest(BaseModel):
    title: str = ""
    product_id: int | None = None
    product_name: str = ""
    channel: str = "local_push"
    hook: str = ""
    pain_point: str = ""
    selling_point: str = ""
    social_proof: str = ""
    call_to_action: str = ""
    full_script: str = ""
    style_notes: str = ""
    hashtags: list | None = None
    suggested_titles: list | None = None
    status: str = "draft"

class ScriptUpdateRequest(BaseModel):
    title: str | None = None
    product_id: int | None = None
    product_name: str | None = None
    channel: str | None = None
    hook: str | None = None
    pain_point: str | None = None
    selling_point: str | None = None
    social_proof: str | None = None
    call_to_action: str | None = None
    full_script: str | None = None
    style_notes: str | None = None
    hashtags: list | None = None
    suggested_titles: list | None = None
    status: str | None = None

class AdCopySaveRequest(BaseModel):
    product_id: int | None = None
    product_name: str = ""
    channel: str = "ocean_engine"
    ad_type: str = "feed"
    title: str = ""
    headline: str = ""
    description: str = ""
    call_to_action: str = "立即购买"
    target_audience_desc: str = ""
    landing_page_suggestion: str = ""
    status: str = "draft"

class AdCopyUpdateRequest(BaseModel):
    product_id: int | None = None
    product_name: str | None = None
    channel: str | None = None
    ad_type: str | None = None
    title: str | None = None
    headline: str | None = None
    description: str | None = None
    call_to_action: str | None = None
    target_audience_desc: str | None = None
    landing_page_suggestion: str | None = None
    status: str | None = None

class CampaignCreateRequest(BaseModel):
    name: str
    channel: str = "local_push"
    status: str = "planning"
    budget: float | None = None
    budget_type: str = "daily"
    start_date: str = ""
    end_date: str = ""
    target_audience: dict | None = None
    product_ids: list | None = None
    script_ids: list | None = None
    ad_copy_ids: list | None = None
    notes: str = ""
    performance_metrics: dict | None = None

class CampaignUpdateRequest(BaseModel):
    name: str | None = None
    channel: str | None = None
    status: str | None = None
    budget: float | None = None
    budget_type: str | None = None
    start_date: str | None = None
    end_date: str | None = None
    target_audience: dict | None = None
    product_ids: list | None = None
    script_ids: list | None = None
    ad_copy_ids: list | None = None
    notes: str | None = None
    performance_metrics: dict | None = None

class AccountCreateRequest(BaseModel):
    channel: str = "local_push"
    account_name: str
    external_account_id: str = ""
    status: str = "active"
    notes: str = ""

class AccountUpdateRequest(BaseModel):
    channel: str | None = None
    account_name: str | None = None
    external_account_id: str | None = None
    status: str | None = None
    notes: str | None = None

class MaterialCreateRequest(BaseModel):
    title: str
    material_type: str = "video"
    channel: str = ""
    source_file_id: int | None = None
    content_url: str = ""
    content_text: str = ""
    status: str = "draft"
    notes: str = ""
    metadata_json: dict | None = None

class MaterialUpdateRequest(BaseModel):
    title: str | None = None
    material_type: str | None = None
    channel: str | None = None
    source_file_id: int | None = None
    content_url: str | None = None
    content_text: str | None = None
    status: str | None = None
    notes: str | None = None
    metadata_json: dict | None = None

class DeliveryTaskCreateRequest(BaseModel):
    task_type: str = "publish_script"
    target_type: str = "campaign"
    target_id: int | None = None
    status: str = "pending"
    priority: int = 5
    payload: dict | None = None
    result_payload: dict | None = None
    error_message: str = ""
    auto_execute: bool = True

class DeliveryTaskUpdateRequest(BaseModel):
    task_type: str | None = None
    target_type: str | None = None
    target_id: int | None = None
    status: str | None = None
    priority: int | None = None
    payload: dict | None = None
    result_payload: dict | None = None
    error_message: str | None = None

class DeliveryTaskStatusRequest(BaseModel):
    status: str
    error_message: str = ""
    result_payload: dict | None = None

class CleanupRequest(BaseModel):
    marker: str

class PromptSaveRequest(BaseModel):
    key: str
    name: str = ""
    content: str
    description: str = ""
    category: str = "custom"
    channel: str = ""


# ── Content Generation endpoints ────────────────────────────────

@router.post("/scripts/generate")
async def api_generate_script(
    payload: ScriptGenerateRequest,
    user: User = Depends(require_permission("editor")),
):
    result = await generate_script(payload.product, payload.channel, user.id)
    return ApiResponse(data=result)


@router.post("/ad-copies/generate")
async def api_generate_ad_copy(
    payload: AdCopyGenerateRequest,
    user: User = Depends(require_permission("editor")),
):
    result = await generate_ad_copy(payload.product, payload.channel, payload.ad_type, user.id)
    return ApiResponse(data=result)


@router.post("/validate")
async def api_validate_content(
    payload: ValidateRequest,
    user: User = Depends(require_permission("editor")),
):
    result = await validate_content(payload.content, user.id)
    return ApiResponse(data=result)


@router.post("/campaigns/{campaign_id}/analyze")
async def api_analyze_campaign(
    campaign_id: int,
    user: User = Depends(require_permission("editor")),
):
    result = await analyze_campaign(campaign_id, user.id)
    if not result:
        from app.core.exceptions import NotFound
        raise NotFound("Campaign not found")
    return ApiResponse(data=result)


# ── Product CRUD ────────────────────────────────────────────────

@router.get("/products")
async def api_list_products(
    user: User = Depends(require_permission("viewer")),
):
    result = await list_products(user.id)
    return ApiResponse(data=result)


@router.post("/products")
async def api_create_product(
    payload: ProductCreateRequest,
    user: User = Depends(require_permission("editor")),
):
    result = await create_product(payload.model_dump(exclude_none=True), user.id)
    return ApiResponse(data=result)


@router.put("/products/{product_id}")
async def api_update_product(
    product_id: int,
    payload: ProductUpdateRequest,
    user: User = Depends(require_permission("editor")),
):
    result = await update_product(product_id, payload.model_dump(exclude_none=True), user.id)
    if not result:
        from app.core.exceptions import NotFound
        raise NotFound("Product not found")
    return ApiResponse(data=result)


@router.delete("/products/{product_id}")
async def api_delete_product(
    product_id: int,
    user: User = Depends(require_permission("editor")),
):
    ok = await delete_product(product_id, user.id)
    if not ok:
        from app.core.exceptions import NotFound
        raise NotFound("Product not found")
    return ApiResponse(data={"deleted": True})


# ── Script CRUD ─────────────────────────────────────────────────

@router.get("/scripts")
async def api_list_scripts(
    channel: str | None = Query(default=None),
    user: User = Depends(require_permission("viewer")),
):
    result = await list_scripts(user.id, channel)
    return ApiResponse(data=result)


@router.get("/scripts/{script_id}")
async def api_get_script(
    script_id: int,
    user: User = Depends(require_permission("viewer")),
):
    result = await get_script(script_id, user.id)
    if not result:
        from app.core.exceptions import NotFound
        raise NotFound("Script not found")
    return ApiResponse(data=result)


@router.post("/scripts")
async def api_save_script(
    payload: ScriptSaveRequest,
    user: User = Depends(require_permission("editor")),
):
    result = await save_script(payload.model_dump(exclude_none=True), user.id)
    return ApiResponse(data=result)


@router.put("/scripts/{script_id}")
async def api_update_script(
    script_id: int,
    payload: ScriptUpdateRequest,
    user: User = Depends(require_permission("editor")),
):
    result = await update_script(script_id, payload.model_dump(exclude_none=True), user.id)
    if not result:
        from app.core.exceptions import NotFound
        raise NotFound("Script not found")
    return ApiResponse(data=result)


@router.delete("/scripts/{script_id}")
async def api_delete_script(
    script_id: int,
    user: User = Depends(require_permission("editor")),
):
    ok = await delete_script(script_id, user.id)
    if not ok:
        from app.core.exceptions import NotFound
        raise NotFound("Script not found")
    return ApiResponse(data={"deleted": True})


# ── Ad Copy CRUD ────────────────────────────────────────────────

@router.get("/ad-copies")
async def api_list_ad_copies(
    channel: str | None = Query(default=None),
    user: User = Depends(require_permission("viewer")),
):
    result = await list_ad_copies(user.id, channel)
    return ApiResponse(data=result)


@router.post("/ad-copies")
async def api_save_ad_copy(
    payload: AdCopySaveRequest,
    user: User = Depends(require_permission("editor")),
):
    result = await save_ad_copy(payload.model_dump(exclude_none=True), user.id)
    return ApiResponse(data=result)


@router.put("/ad-copies/{copy_id}")
async def api_update_ad_copy(
    copy_id: int,
    payload: AdCopyUpdateRequest,
    user: User = Depends(require_permission("editor")),
):
    result = await update_ad_copy(copy_id, payload.model_dump(exclude_none=True), user.id)
    if not result:
        from app.core.exceptions import NotFound
        raise NotFound("Ad copy not found")
    return ApiResponse(data=result)


@router.delete("/ad-copies/{copy_id}")
async def api_delete_ad_copy(
    copy_id: int,
    user: User = Depends(require_permission("editor")),
):
    ok = await delete_ad_copy(copy_id, user.id)
    if not ok:
        from app.core.exceptions import NotFound
        raise NotFound("Ad copy not found")
    return ApiResponse(data={"deleted": True})


# ── Campaign CRUD ───────────────────────────────────────────────

@router.get("/campaigns")
async def api_list_campaigns(
    user: User = Depends(require_permission("viewer")),
):
    result = await list_campaigns(user.id)
    return ApiResponse(data=result)


@router.post("/campaigns")
async def api_create_campaign(
    payload: CampaignCreateRequest,
    user: User = Depends(require_permission("editor")),
):
    result = await create_campaign(payload.model_dump(exclude_none=True), user.id)
    return ApiResponse(data=result)


@router.put("/campaigns/{campaign_id}")
async def api_update_campaign(
    campaign_id: int,
    payload: CampaignUpdateRequest,
    user: User = Depends(require_permission("editor")),
):
    result = await update_campaign(campaign_id, payload.model_dump(exclude_none=True), user.id)
    if not result:
        from app.core.exceptions import NotFound
        raise NotFound("Campaign not found")
    return ApiResponse(data=result)


@router.delete("/campaigns/{campaign_id}")
async def api_delete_campaign(
    campaign_id: int,
    user: User = Depends(require_permission("editor")),
):
    ok = await delete_campaign(campaign_id, user.id)
    if not ok:
        from app.core.exceptions import NotFound
        raise NotFound("Campaign not found")
    return ApiResponse(data={"deleted": True})


# ── Account CRUD ─────────────────────────────────────────────────

@router.get("/accounts")
async def api_list_accounts(
    channel: str | None = Query(default=None),
    user: User = Depends(require_permission("viewer")),
):
    result = await list_accounts(user.id, channel)
    return ApiResponse(data=result)


@router.post("/accounts")
async def api_create_account(
    payload: AccountCreateRequest,
    user: User = Depends(require_permission("editor")),
):
    result = await create_account(payload.model_dump(exclude_none=True), user.id)
    return ApiResponse(data=result)


@router.put("/accounts/{account_id}")
async def api_update_account(
    account_id: int,
    payload: AccountUpdateRequest,
    user: User = Depends(require_permission("editor")),
):
    result = await update_account(account_id, payload.model_dump(exclude_none=True), user.id)
    if not result:
        from app.core.exceptions import NotFound
        raise NotFound("Account not found")
    return ApiResponse(data=result)


@router.delete("/accounts/{account_id}")
async def api_delete_account(
    account_id: int,
    user: User = Depends(require_permission("editor")),
):
    ok = await delete_account(account_id, user.id)
    if not ok:
        from app.core.exceptions import NotFound
        raise NotFound("Account not found")
    return ApiResponse(data={"deleted": True})


# ── Material CRUD ────────────────────────────────────────────────

@router.get("/materials")
async def api_list_materials(
    material_type: str | None = Query(default=None),
    status: str | None = Query(default=None),
    user: User = Depends(require_permission("viewer")),
):
    result = await list_materials(user.id, material_type, status)
    return ApiResponse(data=result)


@router.post("/materials")
async def api_create_material(
    payload: MaterialCreateRequest,
    user: User = Depends(require_permission("editor")),
):
    result = await create_material(payload.model_dump(exclude_none=True), user.id)
    return ApiResponse(data=result)


@router.put("/materials/{material_id}")
async def api_update_material(
    material_id: int,
    payload: MaterialUpdateRequest,
    user: User = Depends(require_permission("editor")),
):
    result = await update_material(material_id, payload.model_dump(exclude_none=True), user.id)
    if not result:
        from app.core.exceptions import NotFound
        raise NotFound("Material not found")
    return ApiResponse(data=result)


@router.delete("/materials/{material_id}")
async def api_delete_material(
    material_id: int,
    user: User = Depends(require_permission("editor")),
):
    ok = await delete_material(material_id, user.id)
    if not ok:
        from app.core.exceptions import NotFound
        raise NotFound("Material not found")
    return ApiResponse(data={"deleted": True})


# ── Delivery Task CRUD/status ────────────────────────────────────

@router.get("/delivery-tasks")
async def api_list_delivery_tasks(
    status: str | None = Query(default=None),
    task_type: str | None = Query(default=None),
    user: User = Depends(require_permission("viewer")),
):
    result = await list_delivery_tasks(user.id, status, task_type)
    return ApiResponse(data=result)


@router.post("/delivery-tasks")
async def api_create_delivery_task(
    payload: DeliveryTaskCreateRequest,
    user: User = Depends(require_permission("editor")),
):
    result = await create_delivery_task(payload.model_dump(exclude_none=True), user.id)
    return ApiResponse(data=result)


@router.put("/delivery-tasks/{task_id}")
async def api_update_delivery_task(
    task_id: int,
    payload: DeliveryTaskUpdateRequest,
    user: User = Depends(require_permission("editor")),
):
    result = await update_delivery_task(task_id, payload.model_dump(exclude_none=True), user.id)
    if not result:
        from app.core.exceptions import NotFound
        raise NotFound("Delivery task not found")
    return ApiResponse(data=result)


@router.post("/delivery-tasks/{task_id}/status")
async def api_mark_delivery_task_status(
    task_id: int,
    payload: DeliveryTaskStatusRequest,
    user: User = Depends(require_permission("editor")),
):
    result = await mark_delivery_task_status(
        task_id,
        user.id,
        payload.status,
        payload.error_message,
        payload.result_payload,
    )
    if not result:
        from app.core.exceptions import NotFound
        raise NotFound("Delivery task not found")
    return ApiResponse(data=result)


@router.delete("/delivery-tasks/{task_id}")
async def api_delete_delivery_task(
    task_id: int,
    user: User = Depends(require_permission("editor")),
):
    ok = await delete_delivery_task(task_id, user.id)
    if not ok:
        from app.core.exceptions import NotFound
        raise NotFound("Delivery task not found")
    return ApiResponse(data={"deleted": True})


@router.post("/cleanup")
async def api_cleanup_marked_data(
    payload: CleanupRequest,
    user: User = Depends(require_permission("editor")),
):
    result = await cleanup_marked_data(user.id, payload.marker)
    return ApiResponse(data=result)


# ── Prompt CRUD ─────────────────────────────────────────────────

@router.get("/prompts")
async def api_list_prompts(
    category: str | None = Query(default=None),
    channel: str | None = Query(default=None),
    user: User = Depends(require_permission("viewer")),
):
    result = await list_prompts(user.id, category, channel)
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

async def _cap_generate_script(params: dict, caller: str) -> dict:
    owner_id = resolve_user_id(caller)
    product = str(params.get("product", "") or "")
    channel = str(params.get("channel", "local_push") or "local_push")
    return await generate_script(product, channel, owner_id)


async def _cap_generate_ad_copy(params: dict, caller: str) -> dict:
    owner_id = resolve_user_id(caller)
    product = str(params.get("product", "") or "")
    channel = str(params.get("channel", "ocean_engine") or "ocean_engine")
    ad_type = str(params.get("ad_type", "feed") or "feed")
    return await generate_ad_copy(product, channel, ad_type, owner_id)


async def _cap_validate_content(params: dict, caller: str) -> dict:
    owner_id = resolve_user_id(caller)
    content = str(params.get("content", "") or "")
    return await validate_content(content, owner_id)


async def _cap_create_delivery_task(params: dict, caller: str) -> dict:
    owner_id = resolve_user_id(caller)
    return await create_delivery_task(params, owner_id)


async def _cap_mark_task_failed(params: dict, caller: str) -> dict:
    owner_id = resolve_user_id(caller)
    task_id = int(params.get("task_id", 0) or 0)
    error_message = str(params.get("error_message", "") or "")
    result = await mark_delivery_task_status(task_id, owner_id, "failed", error_message, params.get("result_payload"))
    if not result:
        from app.core.exceptions import NotFound
        raise NotFound("Delivery task not found")
    return result


async def _cap_cleanup_marked_data(params: dict, caller: str) -> dict:
    owner_id = resolve_user_id(caller)
    marker = str(params.get("marker", "") or "")
    return await cleanup_marked_data(owner_id, marker)


register_capability(
    "douyin-delivery", "generate_script", _cap_generate_script,
    description="根据产品/卖点生成抖音口播脚本（含钩子/痛点/卖点/信任/引导）",
    brief="生成口播脚本",
    parameters={
        "product": {"type": "string", "description": "产品名称或卖点方向"},
        "channel": {"type": "string", "description": "投放渠道: local_push/ocean_engine/qianchuan"},
    },
    min_role="editor",
)
register_capability(
    "douyin-delivery", "generate_ad_copy", _cap_generate_ad_copy,
    description="根据产品和渠道生成抖音广告文案（标题/描述/定向建议）",
    brief="生成广告文案",
    parameters={
        "product": {"type": "string", "description": "产品名称或卖点"},
        "channel": {"type": "string", "description": "投放渠道"},
        "ad_type": {"type": "string", "description": "广告类型: feed/search/brand"},
    },
    min_role="editor",
)
register_capability(
    "douyin-delivery", "validate_content", _cap_validate_content,
    description="校验投放内容中的成分/功效表述是否科学准确",
    brief="内容校验",
    parameters={"content": {"type": "string", "description": "需要校验的文本"}},
    min_role="editor",
)
register_capability(
    "douyin-delivery", "create_delivery_task", _cap_create_delivery_task,
    description="创建抖音内容交接任务并同步推进状态；不会调用外部广告平台",
    brief="创建交接任务",
    parameters={
        "task_type": {"type": "string", "description": "publish_script/publish_ad_copy/sync_metrics/review_content"},
        "target_type": {"type": "string", "description": "script/ad_copy/campaign/material"},
        "target_id": {"type": "integer", "description": "目标逻辑 ID"},
        "payload": {"type": "object", "description": "交接参数；execution_mode 支持 handoff/dry_run"},
        "auto_execute": {"type": "boolean", "description": "是否创建后立即推进状态，默认 true"},
    },
    min_role="editor",
)
register_capability(
    "douyin-delivery", "mark_task_failed", _cap_mark_task_failed,
    description="把投递任务标记为 failed，并写入 error_message，禁止语义失败假成功",
    brief="标记投递失败",
    parameters={
        "task_id": {"type": "integer", "description": "投递任务 ID"},
        "error_message": {"type": "string", "description": "失败原因"},
        "result_payload": {"type": "object", "description": "可选失败上下文"},
    },
    min_role="editor",
)
register_capability(
    "douyin-delivery", "cleanup_marked_data", _cap_cleanup_marked_data,
    description="按 marker 清理当前用户测试数据，marker 至少 6 字符",
    brief="清理测试数据",
    parameters={"marker": {"type": "string", "description": "测试数据标记，至少 6 字符"}},
    min_role="editor",
)
