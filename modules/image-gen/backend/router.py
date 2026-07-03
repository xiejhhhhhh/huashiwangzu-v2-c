"""FastAPI router for image-gen module.

Multi-provider template adapter architecture.
"""
import io
import json
import logging
import re
import time
import uuid

from app.core.exceptions import AppException, ValidationError
from app.database import AsyncSessionLocal, engine
from app.middleware.auth import require_permission
from app.models.user import User
from app.schemas.common import ApiResponse
from app.services.file_reader import resolve_caller_user_id
from app.services.module_registry import register_capability
from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import Column, DateTime, Integer, Text, desc, func, select
from sqlalchemy.orm import declarative_base

from .providers import (
    get_default_template,
    get_provider,
    list_templates,
    resolve_provider,
)
from .providers.base import GenSpec

logger = logging.getLogger("v2.image-gen").getChild("router")

router = APIRouter(prefix="/api/image-gen", tags=["image-gen"])

MIN_IMAGE_DIMENSION = 256
MAX_IMAGE_DIMENSION = 2048
MAX_IMAGE_COUNT = 4
MIN_STEPS = 1
MAX_STEPS = 100

# ---------------------------------------------------------------------------
# imagegen_records table (lightweight cost tracking)
# ---------------------------------------------------------------------------

_Base = declarative_base()


class ImageGenRecord(_Base):
    __tablename__ = "imagegen_records"

    id = Column(Integer, primary_key=True, autoincrement=True)
    owner_id = Column(Integer, nullable=False, index=True)
    template = Column(Text, nullable=False)
    prompt = Column(Text, nullable=False)
    image_count = Column(Integer, nullable=False, default=0)
    points_cost = Column(Integer, nullable=True)
    balance_after = Column(Integer, nullable=True)
    file_ids = Column(Text, nullable=True)
    status = Column(Text, nullable=False, default="success")
    error_msg = Column(Text, nullable=True)
    created_at = Column(DateTime, server_default=func.now())


def _ensure_tables():
    import asyncio

    async def _init():
        try:
            async with engine.begin() as conn:
                await conn.run_sync(_Base.metadata.create_all)
            logger.info("imagegen_records table ensured")
        except Exception as e:
            logger.warning("Failed to ensure imagegen_records table: %s", e)

    try:
        loop = asyncio.get_event_loop()
    except RuntimeError:
        loop = None

    if loop is not None and loop.is_running():
        asyncio.ensure_future(_init())
    else:
        try:
            asyncio.run(_init())
        except Exception as e:
            logger.warning("Startup init failed: %s", e)


_ensure_tables()

# ---------------------------------------------------------------------------
# Translation helper
# ---------------------------------------------------------------------------

async def _translate_to_english(chinese_prompt: str) -> str:
    from app.gateway.router import gateway_router

    messages = [
        {
            "role": "system",
            "content": "You are an AI painting prompt translator. Translate the user's Chinese requirement into a concise English painting prompt. Output ONLY the English prompt, no explanations, no prefixes.",
        },
        {"role": "user", "content": chinese_prompt},
    ]
    try:
        result = await gateway_router.chat(messages, profile_key="deepseek-v4-flash")
        content = result.get("content", "").strip()
        if content:
            logger.info("Translated prompt: %r -> %r", chinese_prompt[:60], content[:120])
            return content
    except Exception as e:
        logger.warning("Prompt translation failed: %s", e)
    return chinese_prompt


def _parse_bounded_int(value: object, field_name: str, minimum: int, maximum: int) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError) as exc:
        raise ValidationError(f"{field_name} must be an integer") from exc
    if parsed < minimum or parsed > maximum:
        raise ValidationError(f"{field_name} must be between {minimum} and {maximum}")
    return parsed


def _dimensions_from_aspect_ratio(aspect_ratio: str) -> tuple[int, int]:
    normalized = aspect_ratio.strip().lower()
    aspect_map = {
        "square": (1024, 1024),
        "portrait": (768, 1024),
        "landscape": (1280, 720),
        "1:1": (1024, 1024),
        "3:4": (768, 1024),
        "16:9": (1280, 720),
    }
    if normalized in aspect_map:
        return aspect_map[normalized]

    if ":" not in normalized:
        raise ValidationError("Invalid aspect_ratio; expected square, portrait, landscape, or W:H")
    try:
        raw_w, raw_h = normalized.split(":", 1)
        ratio_w, ratio_h = float(raw_w), float(raw_h)
    except ValueError as exc:
        raise ValidationError("Invalid aspect_ratio; expected numeric W:H") from exc
    if ratio_w <= 0 or ratio_h <= 0:
        raise ValidationError("Invalid aspect_ratio; values must be positive")

    if ratio_w >= ratio_h:
        width = 1024
        height = round(width * ratio_h / ratio_w)
    else:
        height = 1024
        width = round(height * ratio_w / ratio_h)
    width = max(MIN_IMAGE_DIMENSION, min(MAX_IMAGE_DIMENSION, width))
    height = max(MIN_IMAGE_DIMENSION, min(MAX_IMAGE_DIMENSION, height))
    return width, height


def _resolve_dimensions(size: str, aspect_ratio: str | None) -> tuple[int, int]:
    if aspect_ratio:
        return _dimensions_from_aspect_ratio(aspect_ratio)

    match = re.match(r"^(\d+)\s*[xX]\s*(\d+)$", size)
    if not match:
        raise ValidationError("Invalid size format; expected e.g. 1024x1024, or provide aspect_ratio")

    width, height = int(match.group(1)), int(match.group(2))
    if (
        width < MIN_IMAGE_DIMENSION
        or width > MAX_IMAGE_DIMENSION
        or height < MIN_IMAGE_DIMENSION
        or height > MAX_IMAGE_DIMENSION
    ):
        raise ValidationError(
            f"size dimensions must be between {MIN_IMAGE_DIMENSION} and {MAX_IMAGE_DIMENSION}"
        )
    return width, height


# ---------------------------------------------------------------------------
# Core capability: generate
# ---------------------------------------------------------------------------

async def _generate(params: dict, caller: str) -> dict:
    prompt = str(params.get("prompt", "")).strip()
    size = str(params.get("size", "1024x1024")).strip()
    aspect_ratio = str(params.get("aspect_ratio", "")).strip() or None
    count = _parse_bounded_int(params.get("count", 1), "count", 1, MAX_IMAGE_COUNT)
    steps = _parse_bounded_int(params.get("steps", 30), "steps", MIN_STEPS, MAX_STEPS)
    template_key = str(params.get("template", "")).strip() or get_default_template()

    if not prompt:
        raise ValidationError("prompt is required")

    user_id = resolve_caller_user_id(caller)
    width, height = _resolve_dimensions(size, aspect_ratio)

    try:
        provider, template_cfg, is_placeholder = resolve_provider(template_key)
    except ValueError:
        raise ValidationError(f"Unknown template: {template_key}")

    if not is_placeholder:
        prompt_language = template_cfg.get("prompt_language", "any")
        if prompt_language == "en" and any(ord(c) > 127 for c in prompt):
            translated = await _translate_to_english(prompt)
            if translated != prompt:
                logger.info("Prompt auto-translated from Chinese to English")
            prompt = translated

    spec = GenSpec(
        prompt=prompt,
        width=width,
        height=height,
        count=count,
        steps=steps,
        aspect_ratio=aspect_ratio,
        template_config=template_cfg,
    )

    try:
        gen_results = await provider.generate(spec)
    except NotImplementedError:
        fallback_provider = get_provider("placeholder")
        gen_results = await fallback_provider.generate(spec)
        is_placeholder = True
        logger.info("Fell back to placeholder for template=%s", template_key)
    except RuntimeError as e:
        error_msg = str(e)
        logger.error("Image generation failed for template=%s: %s", template_key, error_msg)
        friendly = "生图失败，请稍后重试"
        if any(kw in error_msg.lower() for kw in ("timeout", "timed out", "time out")):
            friendly = "生图超时，请稍后重试"
        elif any(kw in error_msg.lower() for kw in ("rate limit", "rate_limit", "too many")):
            friendly = "生图请求过于频繁，请稍后重试"
        elif any(kw in error_msg.lower() for kw in ("auth", "key", "credential", "unauthorized")):
            friendly = "生图服务认证失败，请联系管理员"

        await _save_record(
            owner_id=user_id, template=template_key, prompt=spec.prompt,
            image_count=0, file_ids=None, status="failed", error_msg=error_msg,
        )
        raise ValidationError(friendly) from e
    except Exception as e:
        error_msg = str(e)
        logger.exception("Unexpected error in image generation: %s", error_msg)
        await _save_record(
            owner_id=user_id, template=template_key, prompt=spec.prompt,
            image_count=0, file_ids=None, status="failed", error_msg=error_msg,
        )
        raise ValidationError("生图异常，请稍后重试") from e

    from app.services.file_upload_service import upload_file

    ts = int(time.time() * 1000)
    request_suffix = uuid.uuid4().hex[:8]
    results = []
    file_ids: list[int] = []
    persist_errors: list[str] = []
    generated_placeholder = is_placeholder
    async with AsyncSessionLocal() as db:
        for idx, gen_result in enumerate(gen_results):
            image_bytes = gen_result.image_bytes
            result_placeholder = is_placeholder or bool(gen_result.meta.get("placeholder"))
            generated_placeholder = generated_placeholder or result_placeholder

            if image_bytes is None and gen_result.image_url:
                import httpx
                try:
                    async with httpx.AsyncClient(timeout=httpx.Timeout(30.0)) as client:
                        resp = await client.get(gen_result.image_url)
                        resp.raise_for_status()
                        image_bytes = resp.content
                except Exception as e:
                    err = f"download failed for image {idx + 1}: {e}"
                    persist_errors.append(err)
                    logger.warning("Failed to download image from URL %s: %s", gen_result.image_url, e)
                    continue

            if image_bytes is None:
                persist_errors.append(f"image {idx + 1} returned no bytes or URL")
                continue

            filename = f"image-gen_{ts}_{request_suffix}_{idx + 1}.png"
            file_obj = io.BytesIO(image_bytes)
            try:
                upload_result = await upload_file(
                    db, file_obj, filename, user_id, folder_id=None,
                )
            except Exception as e:
                err = f"save failed for image {idx + 1}: {e}"
                persist_errors.append(err)
                logger.warning("Failed to save generated image %d: %s", idx + 1, e)
                continue
            file_ids.append(upload_result["id"])
            entry: dict = {
                "type": "image",
                "file_id": upload_result["id"],
                "name": upload_result["name"],
                "size": upload_result["size"],
                "placeholder": result_placeholder,
            }
            if result_placeholder:
                entry["explanation"] = "占位图，真实生成待接入"
            results.append(entry)

    if not results:
        error_msg = "; ".join(persist_errors) or "image generation produced no downloadable images"
        await _save_record(
            owner_id=user_id, template=template_key, prompt=spec.prompt,
            image_count=0, file_ids=None, status="failed", error_msg=error_msg,
        )
        raise ValidationError("生图失败：未生成可用图片")

    points_cost = None
    balance = None
    if gen_results and gen_results[0].meta:
        points_cost = gen_results[0].meta.get("points_cost")
        balance = gen_results[0].meta.get("balance")

    await _save_record(
        owner_id=user_id, template=template_key, prompt=spec.prompt,
        image_count=len(results), file_ids=file_ids,
        status="partial" if persist_errors else ("placeholder" if generated_placeholder else "success"),
        error_msg="; ".join(persist_errors) if persist_errors else None,
        points_cost=points_cost, balance_after=balance,
    )

    response = {
        "images": results,
        "placeholder": generated_placeholder,
        "template": template_key,
        "points_cost": points_cost,
        "balance": balance,
    }
    if persist_errors:
        response["error"] = "部分图片保存失败，已返回可用结果"
        response["detail"] = "; ".join(persist_errors)
    return response


async def _save_record(
    owner_id: int, template: str, prompt: str,
    image_count: int, file_ids: list[int] | None,
    status: str, error_msg: str | None = None,
    points_cost: int | None = None, balance_after: int | None = None,
):
    try:
        async with AsyncSessionLocal() as db:
            from sqlalchemy import insert
            stmt = insert(ImageGenRecord).values(
                owner_id=owner_id,
                template=template,
                prompt=prompt[:500],
                image_count=image_count,
                file_ids=json.dumps(file_ids) if file_ids else None,
                status=status,
                error_msg=error_msg,
                points_cost=points_cost,
                balance_after=balance_after,
            )
            await db.execute(stmt)
            await db.commit()
    except Exception as e:
        logger.warning("Failed to save imagegen record: %s", e)


# ---------------------------------------------------------------------------
# Capability: list_templates
# ---------------------------------------------------------------------------

async def _list_templates(params: dict, caller: str) -> dict:
    templates = list_templates()
    return {"templates": templates}


# ---------------------------------------------------------------------------
# Capability: usage_history
# ---------------------------------------------------------------------------

async def _usage_history(params: dict, caller: str) -> dict:
    user_id = resolve_caller_user_id(caller)
    limit = min(int(params.get("limit", 20)), 100)
    try:
        async with AsyncSessionLocal() as db:
            stmt = (
                select(ImageGenRecord)
                .where(ImageGenRecord.owner_id == user_id)
                .order_by(desc(ImageGenRecord.id))
                .limit(limit)
            )
            result = await db.execute(stmt)
            rows = result.scalars().all()
            records = []
            for r in rows:
                records.append({
                    "id": r.id,
                    "template": r.template,
                    "prompt": r.prompt,
                    "image_count": r.image_count,
                    "points_cost": r.points_cost,
                    "balance_after": r.balance_after,
                    "status": r.status,
                    "error_msg": r.error_msg,
                    "created_at": str(r.created_at) if r.created_at else None,
                })
            return {"records": records}
    except Exception as e:
        logger.warning("Failed to query usage history: %s", e)
        raise AppException("生图历史查询失败") from e


# ---------------------------------------------------------------------------
# HTTP endpoints
# ---------------------------------------------------------------------------

class GenerateRequest(BaseModel):
    prompt: str
    size: str = "1024x1024"
    aspect_ratio: str | None = None
    count: int = 1
    steps: int = 30
    template: str = ""


@router.get("/health")
async def health():
    return ApiResponse(data={"module": "image-gen", "status": "ok"})


@router.post("/generate")
async def call_generate(
    payload: GenerateRequest,
    user: User = Depends(require_permission("editor")),
):
    result = await _generate(payload.model_dump(), f"user:{user.id}")
    return ApiResponse(data=result)


@router.get("/templates")
async def call_list_templates(
    user: User = Depends(require_permission("viewer")),
):
    result = await _list_templates({}, f"user:{user.id}")
    return ApiResponse(data=result)


@router.get("/history")
async def call_usage_history(
    limit: int = 20,
    user: User = Depends(require_permission("editor")),
):
    result = await _usage_history({"limit": limit}, f"user:{user.id}")
    return ApiResponse(data=result)


# ---------------------------------------------------------------------------
# Register capabilities (Agent discovers these automatically)
# ---------------------------------------------------------------------------

register_capability(
    "image-gen", "generate", _generate,
    description="生成图片：根据提示词生成产品图、海报、配图等（多服务商模板，支持LiblibAI星流/GPTStore/占位图降级）",
    brief="按提示词生成图片",
    parameters={
        "prompt": {"type": "string", "description": "提示词，描述想要生成的图片内容。支持中文（会自动翻译成英文提示词）"},
        "size": {"type": "string", "description": "尺寸，格式如 1024x1024", "default": "1024x1024"},
        "aspect_ratio": {"type": "string", "description": "宽高比，可选 square/portrait/landscape 或如 16:9, 3:4", "default": ""},
        "count": {"type": "integer", "description": "生成数量（1-4）", "default": 1},
        "steps": {"type": "integer", "description": "采样步数", "default": 30},
        "template": {"type": "string", "description": "模板key，可选值由list_templates给出，缺省用默认模板", "default": ""},
    },
    min_role="editor",
)

register_capability(
    "image-gen", "list_templates", _list_templates,
    description="列出可用生图模板（服务商+模型），含凭据是否齐全标识",
    brief="列出可用生图模板",
    parameters={},
    min_role="viewer",
)

register_capability(
    "image-gen", "usage_history", _usage_history,
    description="查询本人的生图历史记录，含积分消耗",
    brief="生图历史记录",
    parameters={
        "limit": {"type": "integer", "description": "返回条数", "default": 20},
    },
    min_role="editor",
)
