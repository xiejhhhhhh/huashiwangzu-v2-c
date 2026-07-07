from __future__ import annotations

import hashlib
import io
from contextlib import contextmanager
from typing import Any

from app.gateway.config import get_model_type_config

PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"
PNG_TEXT_CHUNKS = {b"tEXt", b"zTXt", b"iTXt"}
VISION_IMAGE_PREPROCESS_VERSION = "vision_image_preprocess_v2"


@contextmanager
def allow_large_image_decode(image_module):
    """Allow trusted local images to open so they can be downscaled before VLM."""
    previous_limit = image_module.MAX_IMAGE_PIXELS
    image_module.MAX_IMAGE_PIXELS = None
    try:
        yield
    finally:
        image_module.MAX_IMAGE_PIXELS = previous_limit


def strip_png_text_chunks(image_bytes: bytes) -> tuple[bytes, dict[str, Any]]:
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
                diagnostics["removed_chunks"] += 1
                diagnostics["removed_bytes"] += chunk_end - chunk_start
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


def vision_image_preprocess_config() -> dict[str, Any]:
    config = get_model_type_config("vision").get("image_preprocess", {})
    return config if isinstance(config, dict) else {}


def preprocess_int(config: dict[str, Any], key: str, default: int, minimum: int, maximum: int) -> int:
    try:
        value = int(config.get(key, default))
    except (TypeError, ValueError):
        return default
    return max(minimum, min(maximum, value))


def prepare_vision_image_for_model(
    image_bytes: bytes,
    mime_type: str,
    *,
    max_dimension: int = 1600,
    max_bytes: int = 1024 * 1024,
    jpeg_quality_start: int = 84,
    jpeg_quality_floor: int = 72,
) -> tuple[bytes, str, dict[str, Any]]:
    """Resize/compress images before embedding them in multimodal requests."""
    metadata: dict[str, Any] = {
        "version": VISION_IMAGE_PREPROCESS_VERSION,
        "original_bytes": len(image_bytes),
        "prepared_bytes": len(image_bytes),
        "original_md5": hashlib.md5(image_bytes).hexdigest(),
        "original_mime_type": mime_type,
        "prepared_mime_type": mime_type,
        "vlm_ready": False,
        "resized": False,
        "reencoded": False,
    }
    try:
        from PIL import Image
    except Exception as exc:
        metadata["target_max_bytes"] = max_bytes
        metadata["send_blocked"] = len(image_bytes) > max_bytes
        metadata["skipped_reason"] = f"pillow_unavailable:{exc}"
        return image_bytes, mime_type, metadata

    if mime_type.lower() in {"image/png", "png"} or image_bytes.startswith(PNG_SIGNATURE):
        cleaned_bytes, cleanup_info = strip_png_text_chunks(image_bytes)
        if cleanup_info.get("stripped"):
            image_bytes = cleaned_bytes
            metadata["png_text_chunk_cleanup"] = cleanup_info

    try:
        with allow_large_image_decode(Image):
            with Image.open(io.BytesIO(image_bytes)) as img:
                original_size = tuple(img.size)
                metadata["original_size"] = list(original_size)
                working = img.copy()
    except Exception as exc:
        metadata["target_max_bytes"] = max_bytes
        metadata["send_blocked"] = len(image_bytes) > max_bytes
        metadata["skipped_reason"] = f"unreadable_image:{exc}"
        return image_bytes, mime_type, metadata

    width, height = working.size
    longest = max(width, height)
    if longest > max_dimension:
        scale = max_dimension / longest
        new_size = (max(1, round(width * scale)), max(1, round(height * scale)))
        working = working.resize(new_size, Image.Resampling.LANCZOS)
        metadata["resized"] = True
        metadata["prepared_size"] = list(new_size)
    else:
        metadata["prepared_size"] = [width, height]

    original_can_pass = (
        not metadata["resized"]
        and len(image_bytes) <= max_bytes
        and mime_type.lower() in {"image/jpeg", "image/jpg"}
    )
    if original_can_pass:
        metadata["vlm_ready"] = True
        metadata["prepared_md5"] = hashlib.md5(image_bytes).hexdigest()
        return image_bytes, mime_type, metadata

    if working.mode in {"RGBA", "LA"} or (working.mode == "P" and "transparency" in working.info):
        from PIL import Image

        background = Image.new("RGB", working.size, (255, 255, 255))
        alpha = working.convert("RGBA").getchannel("A")
        background.paste(working.convert("RGBA"), mask=alpha)
        working = background
    elif working.mode != "RGB":
        working = working.convert("RGB")

    quality_start = max(40, min(95, int(jpeg_quality_start)))
    quality_floor = max(40, min(quality_start, int(jpeg_quality_floor)))
    quality_steps = [q for q in (quality_start, 78, quality_floor) if quality_floor <= q <= quality_start]
    qualities = sorted(set(quality_steps), reverse=True)
    metadata["jpeg_quality_start"] = quality_start
    metadata["jpeg_quality_floor"] = quality_floor
    metadata["target_max_bytes"] = max_bytes

    prepared = image_bytes
    selected_quality = qualities[-1]

    def encode_jpeg(quality: int) -> bytes:
        out = io.BytesIO()
        working.save(out, format="JPEG", quality=quality, optimize=True)
        return out.getvalue()

    for quality in qualities:
        prepared = encode_jpeg(quality)
        selected_quality = quality
        if len(prepared) <= max_bytes:
            break

    metadata["jpeg_quality"] = selected_quality
    metadata["prepared_size"] = [working.width, working.height]
    metadata["prepared_bytes"] = len(prepared)
    metadata["prepared_mime_type"] = "image/jpeg"
    metadata["prepared_md5"] = hashlib.md5(prepared).hexdigest()
    metadata["vlm_ready"] = True
    metadata["reencoded"] = True
    return prepared, "image/jpeg", metadata


def prepare_vision_image_for_model_from_config(
    image_bytes: bytes,
    mime_type: str,
) -> tuple[bytes, str, dict[str, Any]]:
    config = vision_image_preprocess_config()
    jpeg_quality_start = preprocess_int(config, "jpeg_quality_start", 84, 40, 95)
    return prepare_vision_image_for_model(
        image_bytes,
        mime_type,
        max_dimension=preprocess_int(config, "max_side", 1600, 640, 4096),
        max_bytes=preprocess_int(config, "max_bytes", 1800 * 1024, 256 * 1024, 32 * 1024 * 1024),
        jpeg_quality_start=jpeg_quality_start,
        jpeg_quality_floor=preprocess_int(config, "jpeg_quality_floor", 72, 40, jpeg_quality_start),
    )


def contains_image_payload(value: Any) -> bool:
    if isinstance(value, dict):
        if value.get("type") == "image_url" or "image_url" in value:
            return True
        return any(contains_image_payload(item) for item in value.values())
    if isinstance(value, list):
        return any(contains_image_payload(item) for item in value)
    if isinstance(value, str):
        return value.strip().startswith("data:image/")
    return False


def messages_contain_image_payload(messages: list[dict]) -> bool:
    return any(contains_image_payload(message.get("content")) for message in messages if isinstance(message, dict))
