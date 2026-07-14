from __future__ import annotations

import hashlib
import uuid
from pathlib import Path
from typing import Any

from .providers.base import MediaContext, MediaType, StageResult
from .providers.registry import get_provider, list_providers

IMAGE_EXTENSIONS = {"jpg", "jpeg", "jpe", "jfif", "png", "gif", "webp", "bmp", "ico", "tif", "tiff", "avif"}
VIDEO_EXTENSIONS = {"mp4", "mov", "m4v", "webm", "mkv", "avi"}
MEDIA_EXTENSIONS = IMAGE_EXTENSIONS | VIDEO_EXTENSIONS
SCHEMA_VERSION = "media-intelligence.analysis.v1"
CONTENT_IR_SCHEMA_VERSION = "content-ir/v1"


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
    _attach_content_ir(refined, context)
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
    _attach_content_ir(result, context)
    result["resource_refs"] = _build_resource_refs(result, context)
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


def _build_resource_refs(result: dict[str, Any], context: MediaContext) -> list[dict[str, object]]:
    return [
        {
            "type": "file",
            "id": context.file_id,
            "display_name": context.file_name,
            "mime_type": _mime_type(context.extension, context.media_type),
            "access_scope": "user",
            "provenance": {
                "module": "media-intelligence",
                "action": context.options.get("action"),
                "analysis_id": result.get("analysis_id"),
            },
        },
    ]


def _attach_content_ir(result: dict[str, Any], context: MediaContext) -> None:
    metadata = _metadata_from_result(result)
    source_ref = _base_source_ref(result, context, metadata)
    blocks = _build_blocks(result, context, source_ref)
    adapters = _adapter_statuses(result)
    source = {
        "module": "media-intelligence",
        "file_id": context.file_id,
        "filename": context.file_name,
        "file_name": context.file_name,
        "mime_type": _mime_type(context.extension, context.media_type),
        "extension": context.extension,
        "media_type": context.media_type,
        "size_bytes": context.size_bytes,
        "head_sha256": context.head_sha256,
    }
    for key in (
        "width",
        "height",
        "duration_seconds",
        "frame_rate",
        "frame_count",
        "format",
        "mode",
        "video_codec",
    ):
        if key in metadata:
            source[key] = metadata[key]
    result.update({
        "schema_version": CONTENT_IR_SCHEMA_VERSION,
        "module_schema_version": SCHEMA_VERSION,
        "content_type": "image" if context.media_type == "image" else "mixed",
        "title": context.file_name,
        "source_file_id": context.file_id,
        "source_module": "media-intelligence",
        "parser": f"media-intelligence.{context.options.get('action') or 'analyze'}",
        "source": source,
        "blocks": blocks,
        "resources": [],
        "metadata": {
            "analysis_id": result.get("analysis_id"),
            "action": result.get("action"),
            "media_type": context.media_type,
            "signals": result.get("signals", {}),
            "artifacts": result.get("artifacts", {}),
            "tags": result.get("tags", []),
            "stages": result.get("stages", []),
            "adapters": adapters,
            "degraded": result.get("degraded", []),
            "model_fallback": result.get("model_fallback"),
        },
        "quality": {"confidence": result.get("confidence", 0.0)},
    })


def _build_blocks(result: dict[str, Any], context: MediaContext, source_ref: dict[str, Any]) -> list[dict[str, Any]]:
    summary = str(result.get("summary") or "").strip()
    if not summary:
        summary = f"{context.media_type.title()} file {context.file_name} produced structured media facts."
    if context.media_type == "image":
        return [{
            "type": "image",
            "text": summary,
            "data": {
                "source_ref": source_ref,
                "analysis_id": result.get("analysis_id"),
                "artifacts": result.get("artifacts", {}),
            },
            "source_ref": source_ref,
        }]

    blocks: list[dict[str, Any]] = [{
        "type": "paragraph",
        "text": summary,
        "data": {
            "source_ref": source_ref,
            "analysis_id": result.get("analysis_id"),
            "role": "media_summary",
        },
        "source_ref": source_ref,
    }]
    artifacts = result.get("artifacts") if isinstance(result.get("artifacts"), dict) else {}
    keyframes = artifacts.get("keyframes") if isinstance(artifacts, dict) else []
    if isinstance(keyframes, list):
        for frame in keyframes:
            if not isinstance(frame, dict):
                continue
            timestamp = frame.get("timestamp_seconds")
            frame_ref = {
                **source_ref,
                "frame": {"index": frame.get("index"), "timestamp_seconds": timestamp},
                "timecode": _format_timecode(timestamp),
            }
            blocks.append({
                "type": "paragraph",
                "text": f"Keyframe marker at {frame_ref['timecode']}.",
                "data": {
                    "source_ref": frame_ref,
                    "keyframe": frame,
                    "role": "keyframe_marker",
                },
                "source_ref": frame_ref,
            })
    ocr = artifacts.get("ocr") if isinstance(artifacts, dict) else None
    if isinstance(ocr, dict) and str(ocr.get("text") or "").strip():
        transcript_ref = {**source_ref, "transcript": {"source": "ocr", "language": ocr.get("language")}}
        blocks.append({
            "type": "paragraph",
            "text": str(ocr["text"]),
            "data": {
                "source_ref": transcript_ref,
                "ocr": ocr,
                "role": "transcript",
            },
            "source_ref": transcript_ref,
        })
    if len(blocks) == 1 and result.get("degraded"):
        degraded_ref = {**source_ref, "degraded": True}
        blocks.append({
            "type": "paragraph",
            "text": "Media analysis returned structured degraded reasons; see block metadata for dependency details.",
            "data": {
                "source_ref": degraded_ref,
                "degraded": result.get("degraded", []),
                "role": "degraded_notice",
            },
            "source_ref": degraded_ref,
        })
    return blocks


def _metadata_from_result(result: dict[str, Any]) -> dict[str, Any]:
    signals = result.get("signals")
    if not isinstance(signals, dict):
        return {}
    metadata = signals.get("metadata")
    return metadata if isinstance(metadata, dict) else {}


def _adapter_statuses(result: dict[str, Any]) -> dict[str, dict[str, Any]]:
    adapters: dict[str, dict[str, Any]] = {}
    for stage in result.get("stages", []):
        if not isinstance(stage, dict):
            continue
        stage_name = str(stage.get("stage") or "unknown")
        data = stage.get("data") if isinstance(stage.get("data"), dict) else {}
        adapters[stage_name] = {
            "provider": stage.get("provider"),
            "status": stage.get("status"),
            "confidence": stage.get("confidence", 0.0),
            "model": data.get("model"),
            "warnings": stage.get("warnings", []),
            "degraded": data.get("degraded", []),
        }
    artifacts = result.get("artifacts") if isinstance(result.get("artifacts"), dict) else {}
    ocr = artifacts.get("ocr") if isinstance(artifacts, dict) else None
    if isinstance(ocr, dict):
        adapters["ocr"] = {
            "provider": ocr.get("engine"),
            "status": ocr.get("status", "ok" if ocr.get("text") else "degraded"),
            "language": ocr.get("language"),
        }
    objects = artifacts.get("objects") if isinstance(artifacts, dict) else None
    adapters["object_detection"] = {
        "provider": "local_algorithms",
        "status": "ok" if isinstance(objects, list) and objects else "degraded",
        "count": len(objects) if isinstance(objects, list) else 0,
    }
    return adapters


def _base_source_ref(result: dict[str, Any], context: MediaContext, metadata: dict[str, Any]) -> dict[str, Any]:
    ref: dict[str, Any] = {
        "file_id": context.file_id,
        "filename": context.file_name,
        "media_type": context.media_type,
        "extension": context.extension,
        "analysis_id": result.get("analysis_id"),
    }
    if context.media_type == "image":
        ref["image"] = {
            "width": metadata.get("width"),
            "height": metadata.get("height"),
            "frame_count": metadata.get("frame_count", 1),
        }
    else:
        ref["video"] = {
            "duration_seconds": metadata.get("duration_seconds"),
            "width": metadata.get("width"),
            "height": metadata.get("height"),
            "frame_rate": metadata.get("frame_rate"),
            "frame_count": metadata.get("frame_count"),
        }
    return ref


def _format_timecode(value: object) -> str:
    seconds = 0.0
    if isinstance(value, int | float):
        seconds = max(float(value), 0.0)
    minutes, sec = divmod(seconds, 60)
    hours, minute = divmod(int(minutes), 60)
    return f"{hours:02d}:{minute:02d}:{sec:06.3f}"


def _mime_type(extension: str, media_type: MediaType) -> str:
    normalized = extension.lower().lstrip(".")
    if media_type == "video":
        return f"video/{'quicktime' if normalized == 'mov' else normalized or 'mp4'}"
    if normalized in {"jpg", "jpeg"}:
        return "image/jpeg"
    if normalized:
        return f"image/{normalized}"
    return "image/jpeg"


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
