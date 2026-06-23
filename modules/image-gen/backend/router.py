"""FastAPI router for image-gen module.

Image generation via framework gateway (centralized). Falls back to PIL
placeholder when the gateway's image gen provider is not configured.
"""
import base64
import io
import logging
import re
import time

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import AsyncSessionLocal
from app.middleware.auth import require_permission
from app.models.user import User
from app.schemas.common import ApiResponse
from app.services.module_registry import register_capability

logger = logging.getLogger("v2.image-gen").getChild("router")

router = APIRouter(prefix="/api/image-gen", tags=["image-gen"])


# ---------------------------------------------------------------------------
# Real model adapter — GPTStore /v1/responses (gpt-5.5 + image_generation)
# ---------------------------------------------------------------------------

async def _call_image_model(
    prompt: str,
    size: str = "1024x1024",
    style: str = "",
    count: int = 1,
) -> list[bytes]:
    """Call image generation through framework gateway instead of direct httpx.

    Returns list of decoded PNG bytes.

    Raises:
        NotImplementedError — gateway image gen not configured.
        RuntimeError — all retries exhausted on transient errors.
    """
    from app.gateway.router import gateway_router

    result = await gateway_router.generate_image(
        prompt=prompt, size=size, count=count,
    )

    images: list[bytes] = []
    for img_data in result.get("images", []):
        b64_str = img_data.get("b64", "")
        if b64_str:
            images.append(base64.b64decode(b64_str))

    if not images:
        if "error" in result:
            raise RuntimeError(result["error"])
        raise RuntimeError("No images returned from gateway")

    return images


# ---------------------------------------------------------------------------
# Caller helper
# ---------------------------------------------------------------------------

def _resolve_user_id(caller: str) -> int:
    from app.core.exceptions import PermissionDenied
    try:
        prefix, raw_id = caller.split(":", 1)
        if prefix == "user":
            return int(raw_id)
    except (TypeError, ValueError):
        pass
    raise PermissionDenied("Invalid caller")


# ---------------------------------------------------------------------------
# PIL placeholder image generation (fallback when no API key)
# ---------------------------------------------------------------------------

def _make_placeholder(prompt: str, width: int, height: int) -> bytes:
    from PIL import Image, ImageDraw, ImageFont

    img = Image.new("RGB", (width, height), (245, 245, 245))
    draw = ImageDraw.Draw(img)

    watermark_text = "图片生成功能开发中"
    prompt_display = prompt if len(prompt) <= 60 else prompt[:57] + "..."

    font_large = None
    font_small = None
    for font_path in (
        "/System/Library/Fonts/PingFang.ttc",
        "/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc",
        "/usr/share/fonts/noto-cjk/NotoSansCJK-Regular.ttc",
    ):
        try:
            font_large = ImageFont.truetype(font_path, 32)
            font_small = ImageFont.truetype(font_path, 24)
            break
        except (OSError, IOError):
            continue
    if font_large is None:
        font_large = ImageFont.load_default()
        font_small = ImageFont.load_default()

    bbox = draw.textbbox((0, 0), prompt_display, font=font_large)
    tw = bbox[2] - bbox[0]
    th = bbox[3] - bbox[1]
    tx = (width - tw) // 2
    ty = (height - th) // 2 - 30
    draw.text((tx, ty), prompt_display, fill=(60, 60, 60), font=font_large)

    wbbox = draw.textbbox((0, 0), watermark_text, font=font_small)
    ww = wbbox[2] - wbbox[0]
    wh = wbbox[3] - wbbox[1]
    wx = (width - ww) // 2
    wy = ty + th + 40
    draw.text((wx, wy), watermark_text, fill=(160, 160, 160), font=font_small)

    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


# ---------------------------------------------------------------------------
# Capability handler
# ---------------------------------------------------------------------------

async def _generate(params: dict, caller: str) -> dict:
    prompt = str(params.get("prompt", ""))
    size = str(params.get("size", "1024x1024"))
    style = str(params.get("style", ""))
    count = int(params.get("count", 1))

    if not prompt.strip():
        from app.core.exceptions import ValidationError
        raise ValidationError("prompt is required")

    match = re.match(r"^(\d+)\s*[xX]\s*(\d+)$", size.strip())
    if not match:
        from app.core.exceptions import ValidationError
        raise ValidationError("Invalid size format; expected e.g. 1024x1024")
    width, height = int(match.group(1)), int(match.group(2))

    user_id = _resolve_user_id(caller)

    is_placeholder = False
    try:
        image_bytes_list = await _call_image_model(prompt, size, style, count)
    except NotImplementedError:
        image_bytes_list = [_make_placeholder(prompt, width, height)]
        is_placeholder = True
        logger.info(
            "Using placeholder for prompt=%r (GPTSTORE_API_KEY not set)",
            prompt[:80],
        )
    except RuntimeError as e:
        error_msg = str(e)
        logger.error("Image generation failed: %s", error_msg)
        friendly = "生图失败，请稍后重试"
        if any(kw in error_msg.lower() for kw in ("timeout", "timed out", "time out")):
            friendly = "生图超时，请稍后重试"
        elif any(kw in error_msg.lower() for kw in ("rate limit", "rate_limit", "too many")):
            friendly = "生图请求过于频繁，请稍后重试"
        elif any(kw in error_msg.lower() for kw in ("auth", "key", "credential", "unauthorized")):
            friendly = "生图服务认证失败，请联系管理员"
        return {"images": [], "placeholder": False, "error": friendly, "detail": error_msg}

    from app.services.file_upload_service import upload_file

    ts = int(time.time() * 1000)
    results = []
    async with AsyncSessionLocal() as db:
        for idx, img_bytes in enumerate(image_bytes_list):
            filename = f"image-gen_{ts}_{idx+1}.png"
            file_obj = io.BytesIO(img_bytes)
            upload_result = await upload_file(
                db, file_obj, filename, user_id, folder_id=None,
            )
            entry: dict = {
                "type": "image",
                "file_id": upload_result["id"],
                "name": upload_result["name"],
                "size": upload_result["size"],
                "placeholder": is_placeholder,
            }
            if is_placeholder:
                entry["explanation"] = "占位图，真实生成待接入"
            results.append(entry)

    return {"images": results, "placeholder": is_placeholder}


# ---------------------------------------------------------------------------
# HTTP endpoints
# ---------------------------------------------------------------------------

class GenerateRequest(BaseModel):
    prompt: str
    size: str = "1024x1024"
    style: str = ""
    count: int = 1


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


# ---------------------------------------------------------------------------
# Register capability (Agent discovers this automatically)
# ---------------------------------------------------------------------------

register_capability(
    "image-gen", "generate", _generate,
    description="生成图片：根据提示词生成产品图、海报、配图等（通过 GPTStore gpt-5.5 真实生成，无 key 时降级占位图）",
    brief="按提示词生成图片",
    parameters={
        "prompt": {"type": "string", "description": "提示词，描述想要生成的图片内容"},
        "size": {"type": "string", "description": "尺寸，格式如 1024x1024", "default": "1024x1024"},
        "style": {"type": "string", "description": "风格提示词（可选）", "default": ""},
        "count": {"type": "integer", "description": "生成数量（底层 API 限制，可能仅返回一张）", "default": 1},
    },
    min_role="editor",
)
