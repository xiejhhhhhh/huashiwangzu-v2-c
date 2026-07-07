"""Shared diagnostics for parser-extracted embedded resources.

Parsers may still return text blocks successfully when an embedded image cannot
be extracted or persisted. This helper keeps that degraded path visible and
machine-traceable instead of silently swallowing failures.
"""
from __future__ import annotations

import base64
import io
import logging
from collections.abc import Awaitable, Callable
from typing import Any

from app.services.module_registry import call_capability

logger = logging.getLogger("v2.content").getChild("parser_resource_diagnostics")

StoreResourceCallable = Callable[[str, str, dict[str, Any], str], Awaitable[Any]]
PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"
PNG_TEXT_CHUNKS = {b"tEXt", b"zTXt", b"iTXt"}
IMAGE_RESOURCE_MAX_SIDE = 1600
IMAGE_RESOURCE_MAX_BYTES = 1024 * 1024
IMAGE_RESOURCE_QUALITY_STEPS = (84, 78, 72)


def build_resource_diagnostic(
    *,
    stage: str,
    status: str,
    code: str,
    message: str,
    resource: dict[str, Any] | None = None,
    parser: str = "",
    error: Exception | str | None = None,
    location: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build a stable resource diagnostic entry with parser-local location."""
    res = resource or {}
    loc = _compact_dict({
        "resource_id": res.get("id"),
        "page": res.get("page"),
        "filename": res.get("filename"),
        "description": res.get("description") or res.get("text_desc"),
    })
    if location:
        loc.update(_compact_dict(location))

    diagnostic = _compact_dict({
        "parser": parser,
        "stage": stage,
        "status": status,
        "code": code,
        "message": message,
        "resource_ref": res.get("id"),
        "resource_type": res.get("resource_type") or res.get("type"),
        "mime_type": res.get("mime_type"),
        "location": loc,
    })
    if error is not None:
        diagnostic["error_type"] = type(error).__name__ if isinstance(error, Exception) else "Error"
        diagnostic["error_message"] = str(error)
    return diagnostic


async def store_extracted_resources_with_diagnostics(
    result: dict[str, Any],
    *,
    caller: str,
    parser: str,
    store_callable: StoreResourceCallable = call_capability,
) -> dict[str, Any]:
    """Persist parser resources and attach non-fatal diagnostics to the result.

    The parser response keeps `blocks` and `resources` usable even when resource
    storage fails. `_bytes_b64` is always removed before returning.
    """
    diagnostics = _ensure_diagnostic_list(result)
    resources = result.get("resources")
    if not isinstance(resources, list):
        result["resources"] = []
        return result

    for res in resources:
        if not isinstance(res, dict):
            diagnostics.append(build_resource_diagnostic(
                parser=parser,
                stage="store",
                status="failed",
                code="invalid_resource_entry",
                message="Parser returned a non-object resource entry.",
            ))
            continue

        already_diagnosed = bool(res.pop("_resource_diagnostic_recorded", False))
        data_b64 = str(res.pop("_bytes_b64", "") or "")
        if not data_b64:
            if not already_diagnosed:
                diagnostics.append(build_resource_diagnostic(
                    parser=parser,
                    stage="extract",
                    status="degraded",
                    code="resource_bytes_missing",
                    message="Embedded resource metadata was found, but binary bytes were unavailable.",
                    resource=res,
                ))
            continue

        store_payload = _prepare_resource_store_payload(
            res,
            data_b64,
            file_id=result.get("file_id") or result.get("source_file_id"),
        )
        store_action = "store_analysis_resource" if store_payload.get("file_id") else "store_resource"

        try:
            stored = await store_callable(
                "content",
                store_action,
                store_payload,
                caller,
            )
        except Exception as exc:
            logger.warning(
                "Parser resource storage failed parser=%s resource=%s filename=%s: %s",
                parser,
                res.get("id"),
                res.get("filename"),
                exc,
            )
            diagnostics.append(build_resource_diagnostic(
                parser=parser,
                stage="store",
                status="failed",
                code="resource_store_failed",
                message="Embedded resource bytes were extracted, but resource storage failed.",
                resource=res,
                error=exc,
            ))
            continue

        if isinstance(stored, dict) and stored.get("success") is False:
            diagnostics.append(build_resource_diagnostic(
                parser=parser,
                stage="store",
                status="failed",
                code="resource_store_failed",
                message="Resource storage capability returned an explicit failure.",
                resource=res,
                error=str(stored.get("error") or "content:store_resource failed"),
            ))
            continue

        stored_payload = _unwrap_capability_payload(stored)
        stored_id = stored_payload.get("id") if isinstance(stored_payload, dict) else None
        if stored_id is None:
            diagnostics.append(build_resource_diagnostic(
                parser=parser,
                stage="store",
                status="failed",
                code="resource_store_missing_id",
                message="Resource storage completed without a traceable resource id.",
                resource=res,
            ))
            continue
        res["stored_resource_id"] = stored_id
        diagnostics.append(build_resource_diagnostic(
            parser=parser,
            stage="store",
            status="stored",
            code="resource_stored",
            message="Embedded resource was stored successfully.",
            resource=res,
            location={"stored_resource_id": stored_id},
        ))

    return result


def _prepare_resource_store_payload(
    res: dict[str, Any],
    data_b64: str,
    *,
    file_id: Any = None,
) -> dict[str, Any]:
    payload = {
        "data_b64": data_b64,
        "resource_type": res.get("resource_type") or res.get("type") or "image",
        "mime_type": res.get("mime_type", "image/png"),
        "filename": res.get("filename", "resource.png"),
        "description": res.get("description") or res.get("text_desc") or "",
    }
    try:
        normalized_file_id = int(file_id or 0)
    except (TypeError, ValueError):
        normalized_file_id = 0
    if normalized_file_id > 0:
        payload["file_id"] = normalized_file_id
    if res.get("block_id"):
        payload["block_id"] = res.get("block_id")
    if str(payload["resource_type"]).lower() != "image":
        return payload

    prepared = _prepare_image_resource_for_storage(data_b64, str(payload["mime_type"]))
    if prepared is None:
        return payload

    prepared_b64, prepared_mime, diagnostics = prepared
    payload["data_b64"] = prepared_b64
    payload["mime_type"] = prepared_mime
    if prepared_mime == "image/jpeg":
        payload["filename"] = _with_image_extension(str(payload["filename"]), ".jpg")
    res["mime_type"] = payload["mime_type"]
    res["filename"] = payload["filename"]
    res["preprocess"] = diagnostics
    return payload


def _prepare_image_resource_for_storage(data_b64: str, mime_type: str) -> tuple[str, str, dict[str, Any]] | None:
    try:
        image_bytes = base64.b64decode(data_b64, validate=True)
    except Exception:
        return None

    metadata: dict[str, Any] = {
        "phase": "parser_resource_image_preprocess",
        "original_bytes": len(image_bytes),
        "prepared_bytes": len(image_bytes),
        "original_mime_type": mime_type,
        "prepared_mime_type": mime_type,
        "max_side": IMAGE_RESOURCE_MAX_SIDE,
        "target_max_bytes": IMAGE_RESOURCE_MAX_BYTES,
        "jpeg_quality_floor": min(IMAGE_RESOURCE_QUALITY_STEPS),
        "resized": False,
        "reencoded": False,
    }

    if mime_type.lower() in {"image/png", "png"} or image_bytes.startswith(PNG_SIGNATURE):
        cleaned, cleanup = _strip_png_text_chunks(image_bytes)
        if cleanup.get("stripped"):
            image_bytes = cleaned
            metadata["png_text_chunk_cleanup"] = cleanup

    try:
        from PIL import Image
        with Image.open(io.BytesIO(image_bytes)) as image:
            metadata["original_size"] = [int(image.width), int(image.height)]
            working = image.copy()
            original_format = (image.format or "").lower()
    except Exception:
        return None

    longest = max(working.size)
    if longest > IMAGE_RESOURCE_MAX_SIDE:
        scale = IMAGE_RESOURCE_MAX_SIDE / longest
        next_size = (
            max(1, round(working.width * scale)),
            max(1, round(working.height * scale)),
        )
        working = working.resize(next_size, Image.Resampling.LANCZOS)
        metadata["resized"] = True

    metadata["prepared_size"] = [int(working.width), int(working.height)]
    if not metadata["resized"] and len(image_bytes) <= IMAGE_RESOURCE_MAX_BYTES and original_format in {"jpeg", "jpg"}:
        metadata["prepared_bytes"] = len(image_bytes)
        return base64.b64encode(image_bytes).decode("ascii"), mime_type, metadata

    if working.mode in {"RGBA", "LA"} or (working.mode == "P" and "transparency" in working.info):
        background = Image.new("RGB", working.size, (255, 255, 255))
        alpha = working.convert("RGBA").getchannel("A")
        background.paste(working.convert("RGBA"), mask=alpha)
        working = background
    elif working.mode != "RGB":
        working = working.convert("RGB")

    prepared_bytes = image_bytes
    selected_quality = min(IMAGE_RESOURCE_QUALITY_STEPS)
    for quality in IMAGE_RESOURCE_QUALITY_STEPS:
        out = io.BytesIO()
        working.save(out, format="JPEG", quality=quality, optimize=True)
        prepared_bytes = out.getvalue()
        selected_quality = quality
        if len(prepared_bytes) <= IMAGE_RESOURCE_MAX_BYTES:
            break

    metadata["prepared_bytes"] = len(prepared_bytes)
    metadata["prepared_mime_type"] = "image/jpeg"
    metadata["jpeg_quality"] = selected_quality
    metadata["reencoded"] = True
    return base64.b64encode(prepared_bytes).decode("ascii"), "image/jpeg", metadata


def _strip_png_text_chunks(image_bytes: bytes) -> tuple[bytes, dict[str, Any]]:
    diagnostics: dict[str, Any] = {
        "stripped": False,
        "removed_chunks": 0,
        "removed_bytes": 0,
        "original_bytes": len(image_bytes),
        "prepared_bytes": len(image_bytes),
    }
    if not image_bytes.startswith(PNG_SIGNATURE):
        return image_bytes, diagnostics
    output = bytearray(PNG_SIGNATURE)
    offset = len(PNG_SIGNATURE)
    try:
        while offset + 12 <= len(image_bytes):
            chunk_start = offset
            length = int.from_bytes(image_bytes[offset:offset + 4], "big")
            chunk_type = image_bytes[offset + 4:offset + 8]
            chunk_end = offset + 12 + length
            if chunk_end > len(image_bytes):
                return image_bytes, {**diagnostics, "error": "malformed_png_chunk"}
            if chunk_type in PNG_TEXT_CHUNKS:
                diagnostics["stripped"] = True
                diagnostics["removed_chunks"] = int(diagnostics["removed_chunks"]) + 1
                diagnostics["removed_bytes"] = int(diagnostics["removed_bytes"]) + chunk_end - chunk_start
            else:
                output.extend(image_bytes[chunk_start:chunk_end])
            offset = chunk_end
            if chunk_type == b"IEND":
                break
    except Exception as exc:
        return image_bytes, {**diagnostics, "error": str(exc)}
    prepared = bytes(output)
    diagnostics["prepared_bytes"] = len(prepared)
    return prepared, diagnostics


def _with_image_extension(filename: str, extension: str) -> str:
    if "." not in filename.rsplit("/", 1)[-1]:
        return f"{filename}{extension}"
    stem = filename.rsplit(".", 1)[0]
    return f"{stem}{extension}"


def _ensure_diagnostic_list(result: dict[str, Any]) -> list[dict[str, Any]]:
    diagnostics = result.get("resource_diagnostics")
    if isinstance(diagnostics, list):
        return diagnostics
    result["resource_diagnostics"] = []
    return result["resource_diagnostics"]


def _unwrap_capability_payload(value: Any) -> Any:
    if isinstance(value, dict) and isinstance(value.get("data"), dict):
        return value["data"]
    return value


def _compact_dict(value: dict[str, Any]) -> dict[str, Any]:
    return {k: v for k, v in value.items() if v not in (None, "")}
