from __future__ import annotations

import hashlib
import uuid
from pathlib import Path
from typing import Any

from .providers.base import MediaContext, MediaType, StageResult
from .providers.registry import get_provider, list_providers

IMAGE_EXTENSIONS = {"jpg", "jpeg", "png", "gif", "webp", "bmp", "ico"}
VIDEO_EXTENSIONS = {"mp4", "mov", "m4v", "webm", "mkv", "avi"}
MEDIA_EXTENSIONS = IMAGE_EXTENSIONS | VIDEO_EXTENSIONS
SCHEMA_VERSION = "media-intelligence.analysis.v1"


async def analyze_image_path(
    file_id: int,
    file_name: str,
    path: Path,
    extension: str,
    options: dict[str, Any] | None = None,
) -> dict[str, Any]:
    context = build_context(file_id, file_name, path, extension, "image", options, "analyze_image")
    layers = ["local_algorithms", "small_model"]
    if _as_bool(context.options.get("refine"), True):
        layers.append("vlm_refine")
    return await run_pipeline(context, layers)


async def analyze_video_path(
    file_id: int,
    file_name: str,
    path: Path,
    extension: str,
    options: dict[str, Any] | None = None,
) -> dict[str, Any]:
    context = build_context(file_id, file_name, path, extension, "video", options, "analyze_video")
    layers = ["local_algorithms", "small_model"]
    if _as_bool(context.options.get("refine"), True):
        layers.append("vlm_refine")
    return await run_pipeline(context, layers)


async def extract_keyframes_path(
    file_id: int,
    file_name: str,
    path: Path,
    extension: str,
    options: dict[str, Any] | None = None,
) -> dict[str, Any]:
    context = build_context(file_id, file_name, path, extension, "video", options, "extract_keyframes")
    return await run_pipeline(context, ["local_algorithms"])


async def ocr_path(
    file_id: int,
    file_name: str,
    path: Path,
    extension: str,
    media_type: MediaType,
    options: dict[str, Any] | None = None,
) -> dict[str, Any]:
    context = build_context(file_id, file_name, path, extension, media_type, options, "ocr")
    return await run_pipeline(context, ["local_algorithms"])


async def embed_image_path(
    file_id: int,
    file_name: str,
    path: Path,
    extension: str,
    options: dict[str, Any] | None = None,
) -> dict[str, Any]:
    context = build_context(file_id, file_name, path, extension, "image", options, "embed_image")
    return await run_pipeline(context, ["local_algorithms"])


async def detect_objects_path(
    file_id: int,
    file_name: str,
    path: Path,
    extension: str,
    media_type: MediaType,
    options: dict[str, Any] | None = None,
) -> dict[str, Any]:
    context = build_context(file_id, file_name, path, extension, media_type, options, "detect_objects")
    return await run_pipeline(context, ["local_algorithms"])


async def summarize_media_path(
    file_id: int,
    file_name: str,
    path: Path,
    extension: str,
    media_type: MediaType,
    options: dict[str, Any] | None = None,
) -> dict[str, Any]:
    context = build_context(file_id, file_name, path, extension, media_type, options, "summarize_media")
    return await run_pipeline(context, ["local_algorithms", "small_model"])


async def refine_analysis_result(
    analysis: dict[str, Any],
    prompt: str | None = None,
) -> dict[str, Any]:
    refined = dict(analysis)
    source = refined.get("source") if isinstance(refined.get("source"), dict) else {}
    context = MediaContext(
        file_id=int(source.get("file_id", 0) or 0),
        file_name=str(source.get("file_name", "analysis")),
        extension=str(source.get("extension", "")),
        media_type="video" if source.get("media_type") == "video" else "image",
        path=Path("."),
        size_bytes=int(source.get("size_bytes", 0) or 0),
        head_sha256=str(source.get("head_sha256", "")),
        options={"action": "vlm_refine", "prompt": prompt or ""},
    )
    stage = await get_provider("vlm_refine").run(context)
    _merge_stage(refined, stage)
    refined["schema_version"] = SCHEMA_VERSION
    refined["providers"] = list_providers()
    return refined


def build_context(
    file_id: int,
    file_name: str,
    path: Path,
    extension: str,
    media_type: MediaType,
    options: dict[str, Any] | None,
    action: str,
) -> MediaContext:
    normalized_options = dict(options or {})
    normalized_options["action"] = action
    size_bytes = path.stat().st_size
    return MediaContext(
        file_id=file_id,
        file_name=file_name,
        extension=extension.lower().lstrip("."),
        media_type=media_type,
        path=path,
        size_bytes=size_bytes,
        head_sha256=_head_sha256(path),
        options=normalized_options,
    )


async def run_pipeline(context: MediaContext, layers: list[str]) -> dict[str, Any]:
    result = _empty_result(context)
    for layer in layers:
        stage = await get_provider(layer).run(context)
        _merge_stage(result, stage)
    result["confidence"] = _aggregate_confidence(result["stages"])
    return result


def media_type_for_extension(extension: str) -> MediaType:
    normalized = extension.lower().lstrip(".")
    if normalized in IMAGE_EXTENSIONS:
        return "image"
    if normalized in VIDEO_EXTENSIONS:
        return "video"
    raise ValueError(f"Unsupported media extension: {extension}")


def _empty_result(context: MediaContext) -> dict[str, Any]:
    stable_id = uuid.uuid5(
        uuid.NAMESPACE_URL,
        f"media-intelligence:{context.file_id}:{context.head_sha256}:{context.options.get('action')}",
    )
    return {
        "schema_version": SCHEMA_VERSION,
        "analysis_id": str(stable_id),
        "action": context.options.get("action"),
        "media_type": context.media_type,
        "source": {
            "file_id": context.file_id,
            "file_name": context.file_name,
            "extension": context.extension,
            "media_type": context.media_type,
            "size_bytes": context.size_bytes,
            "head_sha256": context.head_sha256,
        },
        "stages": [],
        "signals": {},
        "artifacts": {
            "keyframes": [],
            "ocr": None,
            "objects": [],
            "embedding": None,
        },
        "summary": "",
        "tags": [],
        "confidence": 0.0,
        "warnings": [],
        "degraded": [],
        "model_fallback": None,
        "providers": list_providers(),
    }


def _merge_stage(result: dict[str, Any], stage: StageResult) -> None:
    result["stages"].append(stage.to_dict())
    result["warnings"] = _dedupe([*result.get("warnings", []), *stage.warnings])
    data = stage.data
    if "metadata" in data:
        result["signals"]["metadata"] = data["metadata"]
        source = result.get("source")
        if isinstance(source, dict):
            for key in ("width", "height"):
                if key in data["metadata"]:
                    source[key] = data["metadata"][key]
    if "keyframes" in data:
        result["artifacts"]["keyframes"] = data["keyframes"]
    if "ocr" in data:
        result["artifacts"]["ocr"] = data["ocr"]
    if "objects" in data:
        result["artifacts"]["objects"] = data["objects"]
    if "embedding" in data:
        result["artifacts"]["embedding"] = data["embedding"]
    if "summary" in data:
        result["summary"] = data["summary"]
    if "refined_summary" in data:
        result["summary"] = data["refined_summary"]
    if "tags" in data:
        result["tags"] = _dedupe([*result.get("tags", []), *data["tags"]])
    if "degraded" in data:
        result["degraded"] = _dedupe([*result.get("degraded", []), *data["degraded"]])
    if "model_fallback" in data:
        result["model_fallback"] = data["model_fallback"]


def _aggregate_confidence(stages: list[dict[str, Any]]) -> float:
    if not stages:
        return 0.0
    values = [float(stage.get("confidence", 0.0) or 0.0) for stage in stages]
    return round(sum(values) / len(values), 3)


def _head_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        digest.update(handle.read(65536))
    return digest.hexdigest()


def _as_bool(value: object, default: bool = False) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "y", "on"}
    return bool(value)


def _dedupe(values: list[Any]) -> list[Any]:
    result: list[Any] = []
    for value in values:
        if value not in result:
            result.append(value)
    return result
