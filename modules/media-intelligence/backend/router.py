from __future__ import annotations

from pathlib import Path
from typing import Any, Awaitable, Callable

from app.core.exceptions import ValidationError
from app.middleware.auth import require_permission
from app.models.user import User
from app.schemas.common import ApiResponse
from app.services.module_registry import register_capability
from app.services.uploaded_file_runner import run_uploaded_file_capability
from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from .pipeline import (
    IMAGE_EXTENSIONS,
    MEDIA_EXTENSIONS,
    VIDEO_EXTENSIONS,
    analyze_image_path,
    analyze_video_path,
    detect_objects_path,
    embed_image_path,
    extract_keyframes_path,
    media_type_for_extension,
    ocr_path,
    refine_analysis_result,
    summarize_media_path,
)

router = APIRouter(prefix="/api/media-intelligence", tags=["media-intelligence"])


class AnalyzeRequest(BaseModel):
    file_id: int = Field(gt=0)
    include_embedding: bool = False
    refine: bool = True
    max_keyframes: int = Field(default=5, ge=1, le=12)
    prompt: str | None = None


class KeyframesRequest(BaseModel):
    file_id: int = Field(gt=0)
    max_keyframes: int = Field(default=5, ge=1, le=12)


class FileOnlyRequest(BaseModel):
    file_id: int = Field(gt=0)


class EmbedImageRequest(BaseModel):
    file_id: int = Field(gt=0)
    dimensions: int = Field(default=32, ge=8, le=1024)


class SummarizeRequest(BaseModel):
    file_id: int | None = Field(default=None, gt=0)
    analysis: dict[str, Any] | None = None


class VlmRefineRequest(BaseModel):
    analysis: dict[str, Any]
    prompt: str | None = None


FileHandler = Callable[[int, object, Path, str], Awaitable[dict[str, Any]]]


@router.get("/health")
async def health() -> ApiResponse:
    return ApiResponse(data={"module": "media-intelligence", "status": "ok"})


@router.post("/analyze-image")
async def call_analyze_image(
    payload: AnalyzeRequest,
    user: User = Depends(require_permission("viewer")),
) -> ApiResponse:
    result = await _analyze_image(payload.model_dump(), f"user:{user.id}")
    return ApiResponse(data=result)


@router.post("/analyze-video")
async def call_analyze_video(
    payload: AnalyzeRequest,
    user: User = Depends(require_permission("viewer")),
) -> ApiResponse:
    result = await _analyze_video(payload.model_dump(), f"user:{user.id}")
    return ApiResponse(data=result)


@router.post("/extract-keyframes")
async def call_extract_keyframes(
    payload: KeyframesRequest,
    user: User = Depends(require_permission("viewer")),
) -> ApiResponse:
    result = await _extract_keyframes(payload.model_dump(), f"user:{user.id}")
    return ApiResponse(data=result)


@router.post("/ocr")
async def call_ocr(
    payload: FileOnlyRequest,
    user: User = Depends(require_permission("viewer")),
) -> ApiResponse:
    result = await _ocr(payload.model_dump(), f"user:{user.id}")
    return ApiResponse(data=result)


@router.post("/embed-image")
async def call_embed_image(
    payload: EmbedImageRequest,
    user: User = Depends(require_permission("viewer")),
) -> ApiResponse:
    result = await _embed_image(payload.model_dump(), f"user:{user.id}")
    return ApiResponse(data=result)


@router.post("/detect-objects")
async def call_detect_objects(
    payload: FileOnlyRequest,
    user: User = Depends(require_permission("viewer")),
) -> ApiResponse:
    result = await _detect_objects(payload.model_dump(), f"user:{user.id}")
    return ApiResponse(data=result)


@router.post("/summarize-media")
async def call_summarize_media(
    payload: SummarizeRequest,
    user: User = Depends(require_permission("viewer")),
) -> ApiResponse:
    result = await _summarize_media(payload.model_dump(), f"user:{user.id}")
    return ApiResponse(data=result)


@router.post("/vlm-refine")
async def call_vlm_refine(
    payload: VlmRefineRequest,
    user: User = Depends(require_permission("viewer")),
) -> ApiResponse:
    result = await _vlm_refine(payload.model_dump(), f"user:{user.id}")
    return ApiResponse(data=result)


async def _analyze_image(params: dict[str, Any], caller: str) -> dict[str, Any]:
    params = _file_params(params)

    async def handler(file_id: int, file: object, full_path: Path, ext: str) -> dict[str, Any]:
        return await analyze_image_path(file_id, _file_display_name(file, file_id), full_path, ext, params)

    return await _run_file_action(params, caller, IMAGE_EXTENSIONS, handler)


async def _analyze_video(params: dict[str, Any], caller: str) -> dict[str, Any]:
    params = _file_params(params, max_keyframes=True)

    async def handler(file_id: int, file: object, full_path: Path, ext: str) -> dict[str, Any]:
        return await analyze_video_path(file_id, _file_display_name(file, file_id), full_path, ext, params)

    return await _run_file_action(params, caller, VIDEO_EXTENSIONS, handler)


async def _extract_keyframes(params: dict[str, Any], caller: str) -> dict[str, Any]:
    params = _file_params(params, max_keyframes=True)

    async def handler(file_id: int, file: object, full_path: Path, ext: str) -> dict[str, Any]:
        return await extract_keyframes_path(file_id, _file_display_name(file, file_id), full_path, ext, params)

    return await _run_file_action(params, caller, VIDEO_EXTENSIONS, handler)


async def _ocr(params: dict[str, Any], caller: str) -> dict[str, Any]:
    params = _file_params(params)

    async def handler(file_id: int, file: object, full_path: Path, ext: str) -> dict[str, Any]:
        media_type = media_type_for_extension(ext)
        return await ocr_path(file_id, _file_display_name(file, file_id), full_path, ext, media_type, params)

    return await _run_file_action(params, caller, MEDIA_EXTENSIONS, handler)


async def _embed_image(params: dict[str, Any], caller: str) -> dict[str, Any]:
    params = _file_params(params, dimensions=True)

    async def handler(file_id: int, file: object, full_path: Path, ext: str) -> dict[str, Any]:
        return await embed_image_path(file_id, _file_display_name(file, file_id), full_path, ext, params)

    return await _run_file_action(params, caller, IMAGE_EXTENSIONS, handler)


async def _detect_objects(params: dict[str, Any], caller: str) -> dict[str, Any]:
    params = _file_params(params)

    async def handler(file_id: int, file: object, full_path: Path, ext: str) -> dict[str, Any]:
        media_type = media_type_for_extension(ext)
        return await detect_objects_path(file_id, _file_display_name(file, file_id), full_path, ext, media_type, params)

    return await _run_file_action(params, caller, MEDIA_EXTENSIONS, handler)


async def _summarize_media(params: dict[str, Any], caller: str) -> dict[str, Any]:
    analysis = params.get("analysis")
    if isinstance(analysis, dict):
        source = analysis.get("source") if isinstance(analysis.get("source"), dict) else {}
        summary = str(analysis.get("summary", ""))
        source_ref = {
            "file_id": source.get("file_id"),
            "filename": source.get("filename") or source.get("file_name"),
            "media_type": source.get("media_type"),
            "analysis_id": analysis.get("analysis_id"),
            "transcript": {"source": "existing_analysis_summary"},
        }
        return {
            "schema_version": "content-ir/v1",
            "module_schema_version": "media-intelligence.summary.v1",
            "content_type": "text",
            "title": str(source_ref.get("filename") or "media-summary"),
            "source_file_id": source_ref.get("file_id"),
            "source_module": "media-intelligence",
            "parser": "media-intelligence.summarize_media",
            "source": {
                "module": "media-intelligence",
                "file_id": source_ref.get("file_id"),
                "filename": source_ref.get("filename"),
                "mime_type": None,
            },
            "blocks": [{
                "type": "paragraph",
                "text": summary,
                "data": {"source_ref": source_ref, "role": "summary"},
                "source_ref": source_ref,
            }],
            "resources": [],
            "metadata": {"source_analysis_id": analysis.get("analysis_id")},
            "summary": summary,
            "source_analysis_id": analysis.get("analysis_id"),
            "warnings": ["Summary returned from existing analysis payload."],
        }
    if not params.get("file_id"):
        raise ValidationError("Either file_id or analysis is required")
    params = _file_params(params)

    async def handler(file_id: int, file: object, full_path: Path, ext: str) -> dict[str, Any]:
        media_type = media_type_for_extension(ext)
        return await summarize_media_path(file_id, _file_display_name(file, file_id), full_path, ext, media_type, params)

    return await _run_file_action(params, caller, MEDIA_EXTENSIONS, handler)


async def _vlm_refine(params: dict[str, Any], _caller: str) -> dict[str, Any]:
    analysis = params.get("analysis")
    if not isinstance(analysis, dict):
        raise ValidationError("analysis object is required")
    prompt = params.get("prompt")
    return await refine_analysis_result(analysis, str(prompt) if prompt is not None else None)


async def _run_file_action(
    params: dict[str, Any],
    caller: str,
    allowed_exts: set[str],
    handler: FileHandler,
) -> dict[str, Any]:
    return await run_uploaded_file_capability(params, caller, allowed_exts, handler)


def _file_params(
    params: dict[str, Any],
    *,
    dimensions: bool = False,
    max_keyframes: bool = False,
) -> dict[str, Any]:
    normalized = dict(params)
    normalized["file_id"] = _positive_int(normalized.get("file_id"), "file_id")
    if dimensions:
        normalized["dimensions"] = _bounded_int(
            normalized.get("dimensions", 32),
            "dimensions",
            minimum=8,
            maximum=1024,
        )
    if max_keyframes:
        normalized["max_keyframes"] = _bounded_int(
            normalized.get("max_keyframes", 5),
            "max_keyframes",
            minimum=1,
            maximum=12,
        )
    return normalized


def _positive_int(value: object, name: str) -> int:
    if isinstance(value, bool):
        raise ValidationError(f"{name} must be a positive integer")
    try:
        parsed = int(value)
    except (TypeError, ValueError) as exc:
        raise ValidationError(f"{name} must be a positive integer") from exc
    if parsed <= 0:
        raise ValidationError(f"{name} must be a positive integer")
    return parsed


def _bounded_int(value: object, name: str, *, minimum: int, maximum: int) -> int:
    parsed = _positive_int(value, name)
    if parsed < minimum or parsed > maximum:
        raise ValidationError(f"{name} must be between {minimum} and {maximum}")
    return parsed


def _file_display_name(file: object, file_id: int) -> str:
    name = getattr(file, "name", None)
    extension = getattr(file, "extension", None)
    if name and extension:
        return f"{name}.{extension}"
    if name:
        return str(name)
    return f"file-{file_id}"


READ_MEDIA_CONTRACT = {
    "execution_mode": "sync",
    "resource_class": "local_cpu",
    "timeout_seconds": 120,
    "max_attempts": 1,
    "idempotency": "supported",
    "side_effect_level": "none",
    "output_reference_types": ["file"],
    "parallel_safe": True,
}

VLM_CONTRACT = {
    "execution_mode": "sync",
    "resource_class": "cloud_vlm",
    "timeout_seconds": 240,
    "max_attempts": 1,
    "idempotency": "supported",
    "side_effect_level": "none",
    "output_reference_types": ["file"],
    "parallel_safe": False,
}


register_capability(
    "media-intelligence",
    "analyze_image",
    _analyze_image,
    description="Analyze an uploaded image through local algorithm, small-model, and optional VLM refine layers",
    brief="Analyze image",
    parameters={
        "file_id": {"type": "integer", "description": "Image file ID"},
        "include_embedding": {"type": "bool", "description": "Return local image fingerprint"},
        "refine": {"type": "bool", "description": "Run VLM refine when configured"},
    },
    min_role="viewer",
    execution_contract=VLM_CONTRACT,
    retrieval={
        "aliases": ["看图", "图片理解", "识图", "VLM看图", "分析图片"],
        "when_to_use": "用户上传或引用图片后，需要理解图片内容、场景、主体、文字布局或视觉细节时",
        "when_not_to_use": "用户只需要生成新图片或编辑图片时",
        "input_reference_types": ["file"],
    },
)

register_capability(
    "media-intelligence",
    "analyze_video",
    _analyze_video,
    description="Analyze an uploaded video through local algorithm, small-model, and optional VLM refine layers",
    brief="Analyze video",
    parameters={
        "file_id": {"type": "integer", "description": "Video file ID"},
        "max_keyframes": {"type": "integer", "description": "Maximum timeline keyframe markers"},
        "refine": {"type": "bool", "description": "Run VLM refine when configured"},
    },
    min_role="viewer",
    execution_contract=VLM_CONTRACT,
    retrieval={
        "aliases": ["视频理解", "分析视频", "视频摘要", "VLM看视频"],
        "when_to_use": "用户需要分析视频内容、关键帧、画面摘要或时间线信息时",
        "when_not_to_use": "用户只需要从图片中取字或生成图片时",
        "input_reference_types": ["file"],
    },
)

register_capability(
    "media-intelligence",
    "extract_keyframes",
    _extract_keyframes,
    description="Extract ffprobe-derived timeline keyframe markers from a video file",
    brief="Extract keyframes",
    parameters={
        "file_id": {"type": "integer", "description": "Video file ID"},
        "max_keyframes": {"type": "integer", "description": "Maximum keyframes"},
    },
    min_role="viewer",
    execution_contract=READ_MEDIA_CONTRACT,
    retrieval={
        "aliases": ["视频关键帧", "抽关键帧", "视频帧"],
        "when_to_use": "用户需要从视频中抽取时间线关键帧或定位画面片段时",
        "when_not_to_use": "用户需要完整理解图片或OCR取字时",
        "input_reference_types": ["file"],
    },
)

register_capability(
    "media-intelligence",
    "ocr",
    _ocr,
    description="Run OCR layer contract for image/video files",
    brief="OCR media",
    parameters={"file_id": {"type": "integer", "description": "Image or video file ID"}},
    min_role="viewer",
    execution_contract=READ_MEDIA_CONTRACT,
    retrieval={
        "aliases": ["OCR", "图片取字", "识别文字", "提取图片文字", "截图文字识别"],
        "when_to_use": "用户要求从图片、截图或视频画面中提取文字时",
        "when_not_to_use": "用户要生成或编辑图片时",
        "input_reference_types": ["file"],
    },
)

register_capability(
    "media-intelligence",
    "embed_image",
    _embed_image,
    description="Return a local image fingerprint vector",
    brief="Embed image",
    parameters={
        "file_id": {"type": "integer", "description": "Image file ID"},
        "dimensions": {"type": "integer", "description": "Embedding dimensions"},
    },
    min_role="viewer",
    execution_contract=READ_MEDIA_CONTRACT,
    retrieval={
        "aliases": ["图片向量", "图片指纹", "图片相似"],
        "when_to_use": "需要为图片生成本地指纹、去重或相似检索特征时",
        "when_not_to_use": "用户需要自然语言看图说明或OCR文字时",
        "input_reference_types": ["file"],
    },
)

register_capability(
    "media-intelligence",
    "detect_objects",
    _detect_objects,
    description="Return object detections or a structured degraded result when no detector is configured",
    brief="Detect objects",
    parameters={"file_id": {"type": "integer", "description": "Image or video file ID"}},
    min_role="viewer",
    execution_contract=READ_MEDIA_CONTRACT,
    retrieval={
        "aliases": ["目标检测", "识别物体", "物体检测"],
        "when_to_use": "用户要求列出图片或视频画面中的对象、主体或检测结果时",
        "when_not_to_use": "用户只需要提取文字或生成图片时",
        "input_reference_types": ["file"],
    },
)

register_capability(
    "media-intelligence",
    "summarize_media",
    _summarize_media,
    description="Summarize a media file or existing media-intelligence analysis result",
    brief="Summarize media",
    parameters={
        "file_id": {"type": "integer", "description": "Image or video file ID"},
        "analysis": {"type": "object", "description": "Existing analysis result"},
    },
    min_role="viewer",
    execution_contract=READ_MEDIA_CONTRACT,
    retrieval={
        "aliases": ["媒体总结", "图片总结", "视频总结"],
        "when_to_use": "已有媒体分析结果或用户要求把图片/视频内容总结成文字时",
        "when_not_to_use": "用户需要对图片做二次生图编辑时",
        "input_reference_types": ["file"],
    },
)

register_capability(
    "media-intelligence",
    "vlm_refine",
    _vlm_refine,
    description="Refine an existing media-intelligence analysis result through the VLM layer contract",
    brief="VLM refine",
    parameters={
        "analysis": {"type": "object", "description": "Existing analysis result"},
        "prompt": {"type": "string", "description": "Optional refinement instruction"},
    },
    min_role="viewer",
    execution_contract=VLM_CONTRACT,
    retrieval={
        "aliases": ["VLM精修", "视觉模型补充", "多模态复核"],
        "when_to_use": "已有 media-intelligence 分析结果，需要用 VLM 按提示进一步补充或复核时",
        "when_not_to_use": "没有现成分析对象，且可以直接 analyze_image 时",
        "input_reference_types": ["record"],
    },
)
