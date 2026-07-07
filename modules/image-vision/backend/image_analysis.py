from __future__ import annotations

import hashlib
import math
import threading
from io import BytesIO

from PIL import Image, ImageStat, UnidentifiedImageError

LOCAL_ANALYZER_VERSION = "pillow-local-v1"
MAX_ANALYSIS_SIDE = 128
MAX_FULL_DECODE_PIXELS = 80_000_000
EDGE_THRESHOLD = 18
CONTENT_IR_SCHEMA_VERSION = "content-ir/v1"
_PIL_MAX_PIXELS_LOCK = threading.Lock()
PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"
PNG_TEXT_CHUNKS = {b"tEXt", b"zTXt", b"iTXt"}


def strip_png_text_chunks(raw: bytes) -> tuple[bytes, dict[str, object]]:
    """Remove PNG text metadata chunks while preserving image pixel chunks."""
    diagnostics: dict[str, object] = {
        "stripped": False,
        "removed_chunks": 0,
        "removed_bytes": 0,
        "original_bytes": len(raw),
        "prepared_bytes": len(raw),
    }
    if not raw.startswith(PNG_SIGNATURE):
        return raw, diagnostics

    output = bytearray(PNG_SIGNATURE)
    offset = len(PNG_SIGNATURE)
    try:
        while offset + 12 <= len(raw):
            chunk_start = offset
            length = int.from_bytes(raw[offset:offset + 4], "big")
            chunk_type = raw[offset + 4:offset + 8]
            chunk_end = offset + 12 + length
            if chunk_end > len(raw):
                return raw, {**diagnostics, "error": "malformed_png_chunk"}
            if chunk_type in PNG_TEXT_CHUNKS:
                diagnostics["stripped"] = True
                diagnostics["removed_chunks"] = int(diagnostics["removed_chunks"]) + 1
                diagnostics["removed_bytes"] = int(diagnostics["removed_bytes"]) + (chunk_end - chunk_start)
            else:
                output.extend(raw[chunk_start:chunk_end])
            offset = chunk_end
            if chunk_type == b"IEND":
                break
    except Exception as exc:
        return raw, {**diagnostics, "error": str(exc)}

    prepared = bytes(output)
    diagnostics["prepared_bytes"] = len(prepared)
    return prepared, diagnostics


def _is_png_text_memory_error(exc: Exception) -> bool:
    return "too much memory used in text chunks" in str(exc).lower()


def analyze_image_bytes(raw: bytes, filename: str, ext: str) -> dict[str, object]:
    try:
        with Image.open(BytesIO(raw)) as image:
            width, height = image.size
            if width * height > MAX_FULL_DECODE_PIXELS:
                return _analyze_oversized_image_metadata(
                    image,
                    raw,
                    filename,
                    ext,
                    reason="oversized_image_metadata_only",
                )
            image.load()
            return _analyze_loaded_image(image, raw, filename, ext)
    except ValueError as exc:
        if ext.lower().lstrip(".") == "png" and _is_png_text_memory_error(exc):
            stripped, strip_info = strip_png_text_chunks(raw)
            if stripped is not raw:
                result = analyze_image_bytes(stripped, filename, ext)
                result["png_text_chunk_cleanup"] = strip_info
                return result
        raise ValueError(f"Failed to read image content: {exc}") from exc
    except Image.DecompressionBombError as exc:
        try:
            return _analyze_oversized_image_header(raw, filename, ext, str(exc))
        except UnidentifiedImageError as header_exc:
            raise ValueError("Invalid or unsupported image content") from header_exc
        except OSError as header_exc:
            raise ValueError(f"Failed to read image content: {header_exc}") from header_exc
    except UnidentifiedImageError as exc:
        raise ValueError("Invalid or unsupported image content") from exc
    except OSError as exc:
        raise ValueError(f"Failed to read image content: {exc}") from exc


def should_use_vlm(facts: dict[str, object], mode: str) -> dict[str, object]:
    if mode == "local":
        return {"use_vlm": False, "reason": "local mode requested"}
    if bool(facts.get("metadata_only")) or str(facts.get("visual_profile") or "") == "oversized_image":
        return {"use_vlm": False, "reason": "oversized image analyzed as metadata only"}
    if mode == "semantic":
        return {"use_vlm": True, "reason": "semantic mode requested"}

    quality = _dict_value(facts, "quality")
    dimensions = _dict_value(facts, "dimensions")
    transparency = _dict_value(facts, "transparency")
    visual_profile = str(facts.get("visual_profile") or "unknown")

    pixel_count = _int_value(dimensions, "pixel_count")
    edge_density = _float_value(quality, "edge_density")
    transparent_ratio = _float_value(transparency, "transparent_ratio")
    is_blank_like = bool(quality.get("is_blank_like"))

    if is_blank_like:
        return {"use_vlm": False, "reason": "local analysis detected a blank or near-flat image"}
    if pixel_count <= 4096:
        return {"use_vlm": False, "reason": "small icon-sized image; local facts are sufficient"}
    if transparent_ratio >= 0.18 and pixel_count <= 262144:
        return {"use_vlm": False, "reason": "transparent graphic/icon; local facts are sufficient"}
    if edge_density < 0.015 and visual_profile in {"flat_graphic", "low_detail"}:
        return {"use_vlm": False, "reason": "low-detail graphic; local facts are sufficient"}
    if visual_profile in {"photo_like", "detailed_graphic"}:
        return {"use_vlm": True, "reason": f"{visual_profile} image may need semantic interpretation"}
    return {"use_vlm": False, "reason": "auto mode found no semantic trigger"}


def build_local_summary(facts: dict[str, object]) -> str:
    dimensions = _dict_value(facts, "dimensions")
    color = _dict_value(facts, "color")
    quality = _dict_value(facts, "quality")
    transparency = _dict_value(facts, "transparency")

    width = _int_value(dimensions, "width")
    height = _int_value(dimensions, "height")
    fmt = str(facts.get("format") or "unknown").upper()
    mode = str(facts.get("mode") or "unknown")
    profile = str(facts.get("visual_profile") or "unknown")
    brightness = _float_value(color, "brightness")
    edge_density = _float_value(quality, "edge_density")
    transparent_ratio = _float_value(transparency, "transparent_ratio")
    dominant = color.get("dominant_colors")
    top_color = ""
    if isinstance(dominant, list) and dominant:
        first = dominant[0]
        if isinstance(first, dict):
            top_color = f"，主色 {first.get('hex')} 占比 {first.get('ratio')}"

    alpha_text = ""
    if transparent_ratio > 0:
        alpha_text = f"，透明像素占比 {transparent_ratio}"

    return (
        f"本地图片分析：{fmt}，{width}x{height}px，模式 {mode}，"
        f"视觉轮廓 {profile}，平均亮度 {brightness}，边缘密度 {edge_density}"
        f"{alpha_text}{top_color}。"
    )


def build_vlm_prompt(local_summary: str, extra_prompt: str | None = None) -> str:
    task = (
        "请只补充本地算法无法可靠判断的语义内容，例如画面主体、场景、可读文字、关系和用途。"
        "不要重复尺寸、格式、亮度、颜色统计等本地事实。"
    )
    if extra_prompt:
        task = f"{task}\n额外需求：{extra_prompt.strip()}"
    return f"{task}\n已知本地事实：{local_summary}"


def build_content_ir_output(
    *,
    file_id: int,
    filename: str,
    extension: str,
    description: str,
    local_summary: str,
    local_analysis: dict[str, object],
    resource_id: int | str | None = None,
    semantic_description: str | None = None,
    analysis_strategy: dict[str, object] | None = None,
    model_fallback: dict[str, object] | None = None,
    warnings: list[str] | None = None,
) -> dict[str, object]:
    block_ref: int | str = resource_id if resource_id else 1
    dimensions = _dict_value(local_analysis, "dimensions")
    animation = _dict_value(local_analysis, "animation")
    width = _int_value(dimensions, "width")
    height = _int_value(dimensions, "height")
    frame_count = _int_value(animation, "frame_count") or 1
    source_ref = {
        "file_id": file_id,
        "filename": filename,
        "image": {
            "extension": extension,
            "width": width,
            "height": height,
            "frame_count": frame_count,
        },
    }
    block_data = {
        "source_ref": source_ref,
        "local_analysis": local_analysis,
        "semantic_description": semantic_description,
    }
    blocks = [
        {
            "type": "image",
            "text": description,
            "resource_ref": block_ref,
            "data": block_data,
            "source_ref": source_ref,
        },
        {
            "type": "paragraph",
            "text": local_summary,
            "resource_ref": block_ref,
            "data": {
                "source_ref": source_ref,
                "role": "local_summary",
            },
            "source_ref": source_ref,
        },
    ]
    resources = [
        {
            "id": block_ref,
            "type": "image",
            "resource_type": "image",
            "file_storage_id": file_id,
            "mime_type": _mime_type_for_extension(extension),
            "filename": filename,
            "description": description,
            "text_desc": description,
            "metadata": local_analysis,
            "vlm_metadata": {
                "semantic_description": semantic_description,
                "analysis_strategy": analysis_strategy or {},
                "model_fallback": model_fallback or {},
            },
            "width": width or None,
            "height": height or None,
        },
    ]
    return {
        "schema_version": CONTENT_IR_SCHEMA_VERSION,
        "content_type": "image",
        "title": filename,
        "source_file_id": file_id,
        "source_module": "image-vision",
        "parser": "image-vision.describe",
        "source": {
            "module": "image-vision",
            "file_id": file_id,
            "filename": filename,
            "mime_type": _mime_type_for_extension(extension),
        },
        "blocks": blocks,
        "resources": resources,
        "metadata": {
            "format": extension,
            "analysis_strategy": analysis_strategy or {},
            "model_fallback": model_fallback or {},
            "local_analyzer": str(local_analysis.get("analyzer") or LOCAL_ANALYZER_VERSION),
        },
        "warnings": warnings or [],
        "quality": _dict_value(local_analysis, "quality"),
    }


def _analyze_loaded_image(image: Image.Image, raw: bytes, filename: str, ext: str) -> dict[str, object]:
    width, height = image.size
    rgba = image.convert("RGBA")
    sample = _thumbnail_copy(rgba, MAX_ANALYSIS_SIDE)
    rgb_sample = _composite_on_white(sample)
    gray_sample = rgb_sample.convert("L")

    brightness, contrast = _brightness_stats(gray_sample)
    saturation = _saturation(rgb_sample)
    edge_density = _edge_density(gray_sample)
    transparent_ratio = _transparent_ratio(sample)
    dominant_colors = _dominant_colors(rgb_sample)
    unique_color_estimate = _unique_color_estimate(rgb_sample)
    is_blank_like = _is_blank_like(contrast, edge_density, dominant_colors)
    visual_profile = _visual_profile(
        pixel_count=width * height,
        edge_density=edge_density,
        contrast=contrast,
        saturation=saturation,
        transparent_ratio=transparent_ratio,
        unique_color_estimate=unique_color_estimate,
        is_blank_like=is_blank_like,
    )

    return {
        "analyzer": LOCAL_ANALYZER_VERSION,
        "filename": filename,
        "extension": ext,
        "format": image.format or ext.upper(),
        "mode": image.mode,
        "file_size_bytes": len(raw),
        "sha256": hashlib.sha256(raw).hexdigest(),
        "dimensions": {
            "width": width,
            "height": height,
            "pixel_count": width * height,
            "aspect_ratio": _round(width / height if height else 0),
            "orientation": _orientation(width, height),
        },
        "animation": {
            "is_animated": bool(getattr(image, "is_animated", False)),
            "frame_count": int(getattr(image, "n_frames", 1) or 1),
        },
        "transparency": {
            "has_alpha": _has_alpha(image),
            "transparent_ratio": transparent_ratio,
        },
        "color": {
            "brightness": brightness,
            "contrast": contrast,
            "saturation": saturation,
            "dominant_colors": dominant_colors,
            "unique_color_estimate": unique_color_estimate,
        },
        "quality": {
            "edge_density": edge_density,
            "is_blank_like": is_blank_like,
        },
        "hashes": {
            "average_hash": _average_hash(gray_sample),
            "difference_hash": _difference_hash(gray_sample),
        },
        "visual_profile": visual_profile,
        "exif": {
            "present": bool(image.getexif()),
            "orientation": image.getexif().get(274) if image.getexif() else None,
        },
    }


def _analyze_oversized_image_header(raw: bytes, filename: str, ext: str, reason: str) -> dict[str, object]:
    old_limit = Image.MAX_IMAGE_PIXELS
    with _PIL_MAX_PIXELS_LOCK:
        try:
            Image.MAX_IMAGE_PIXELS = None
            with Image.open(BytesIO(raw)) as image:
                return _analyze_oversized_image_metadata(image, raw, filename, ext, reason=reason)
        finally:
            Image.MAX_IMAGE_PIXELS = old_limit


def _analyze_oversized_image_metadata(
    image: Image.Image,
    raw: bytes,
    filename: str,
    ext: str,
    *,
    reason: str,
) -> dict[str, object]:
    width, height = image.size
    frame_count = int(getattr(image, "n_frames", 1) or 1)
    exif_present = False
    exif_orientation = None
    try:
        exif = image.getexif()
        exif_present = bool(exif)
        exif_orientation = exif.get(274) if exif else None
    except Exception:
        exif_present = False

    return {
        "analyzer": LOCAL_ANALYZER_VERSION,
        "metadata_only": True,
        "metadata_reason": reason,
        "filename": filename,
        "extension": ext,
        "format": image.format or ext.upper(),
        "mode": image.mode,
        "file_size_bytes": len(raw),
        "sha256": hashlib.sha256(raw).hexdigest(),
        "dimensions": {
            "width": width,
            "height": height,
            "pixel_count": width * height,
            "aspect_ratio": _round(width / height if height else 0),
            "orientation": _orientation(width, height),
        },
        "animation": {
            "is_animated": bool(getattr(image, "is_animated", False)),
            "frame_count": frame_count,
        },
        "transparency": {
            "has_alpha": False,
            "transparent_ratio": 0.0,
        },
        "color": {
            "brightness": 0.0,
            "contrast": 0.0,
            "saturation": 0.0,
            "dominant_colors": [],
            "unique_color_estimate": 0,
        },
        "quality": {
            "edge_density": 0.0,
            "is_blank_like": False,
            "metadata_only": True,
        },
        "hashes": {
            "average_hash": "",
            "difference_hash": "",
        },
        "visual_profile": "oversized_image",
        "exif": {
            "present": exif_present,
            "orientation": exif_orientation,
        },
    }


def _mime_type_for_extension(extension: str) -> str:
    normalized = extension.lower().lstrip(".")
    if normalized in {"jpg", "jpeg"}:
        return "image/jpeg"
    if normalized == "png":
        return "image/png"
    if normalized == "gif":
        return "image/gif"
    if normalized == "webp":
        return "image/webp"
    if normalized == "bmp":
        return "image/bmp"
    if normalized == "ico":
        return "image/x-icon"
    return "image/jpeg"


def _thumbnail_copy(image: Image.Image, max_side: int) -> Image.Image:
    copy = image.copy()
    copy.thumbnail((max_side, max_side), Image.Resampling.LANCZOS)
    return copy


def _composite_on_white(image: Image.Image) -> Image.Image:
    background = Image.new("RGBA", image.size, (255, 255, 255, 255))
    return Image.alpha_composite(background, image).convert("RGB")


def _brightness_stats(gray: Image.Image) -> tuple[float, float]:
    stat = ImageStat.Stat(gray)
    mean = stat.mean[0] if stat.mean else 0
    stddev = stat.stddev[0] if stat.stddev else 0
    return _round(mean / 255), _round(stddev / 128)


def _saturation(image: Image.Image) -> float:
    hsv = image.convert("HSV")
    stat = ImageStat.Stat(hsv)
    return _round((stat.mean[1] if stat.mean else 0) / 255)


def _transparent_ratio(image: Image.Image) -> float:
    if "A" not in image.getbands():
        return 0.0
    alpha = image.getchannel("A")
    pixels = alpha.tobytes()
    if not pixels:
        return 0.0
    transparent = sum(1 for value in pixels if value < 250)
    return _round(transparent / len(pixels))


def _dominant_colors(image: Image.Image) -> list[dict[str, object]]:
    quantized = image.quantize(colors=5, method=Image.Quantize.MEDIANCUT)
    palette = quantized.getpalette() or []
    counts = quantized.getcolors(image.width * image.height) or []
    total = max(image.width * image.height, 1)
    colors: list[dict[str, object]] = []
    for count, palette_index in sorted(counts, reverse=True)[:5]:
        offset = palette_index * 3
        if offset + 2 >= len(palette):
            continue
        rgb = palette[offset:offset + 3]
        colors.append({
            "hex": "#{:02x}{:02x}{:02x}".format(rgb[0], rgb[1], rgb[2]),
            "rgb": rgb,
            "ratio": _round(count / total),
        })
    return colors


def _unique_color_estimate(image: Image.Image) -> int:
    colors = image.getcolors(maxcolors=4096)
    if colors is None:
        return 4096
    return len(colors)


def _edge_density(gray: Image.Image) -> float:
    width, height = gray.size
    if width < 2 or height < 2:
        return 0.0
    pixels = gray.load()
    edge_count = 0
    comparisons = 0
    for y in range(height - 1):
        for x in range(width - 1):
            current = pixels[x, y]
            if abs(current - pixels[x + 1, y]) >= EDGE_THRESHOLD:
                edge_count += 1
            if abs(current - pixels[x, y + 1]) >= EDGE_THRESHOLD:
                edge_count += 1
            comparisons += 2
    return _round(edge_count / comparisons if comparisons else 0)


def _average_hash(gray: Image.Image) -> str:
    small = gray.resize((8, 8), Image.Resampling.LANCZOS)
    pixels = list(small.tobytes())
    average = sum(pixels) / len(pixels)
    bits = "".join("1" if value >= average else "0" for value in pixels)
    return _bits_to_hex(bits)


def _difference_hash(gray: Image.Image) -> str:
    small = gray.resize((9, 8), Image.Resampling.LANCZOS)
    pixels = list(small.tobytes())
    bits = []
    for y in range(8):
        row = y * 9
        for x in range(8):
            bits.append("1" if pixels[row + x] > pixels[row + x + 1] else "0")
    return _bits_to_hex("".join(bits))


def _bits_to_hex(bits: str) -> str:
    return f"{int(bits, 2):0{math.ceil(len(bits) / 4)}x}"


def _has_alpha(image: Image.Image) -> bool:
    if image.mode in {"RGBA", "LA"}:
        return True
    if image.mode == "P" and "transparency" in image.info:
        return True
    return "A" in image.getbands()


def _orientation(width: int, height: int) -> str:
    if width == height:
        return "square"
    return "landscape" if width > height else "portrait"


def _is_blank_like(contrast: float, edge_density: float, dominant_colors: list[dict[str, object]]) -> bool:
    top_ratio = 0.0
    if dominant_colors:
        ratio = dominant_colors[0].get("ratio")
        top_ratio = ratio if isinstance(ratio, float | int) else 0.0
    return contrast <= 0.025 and edge_density <= 0.006 and top_ratio >= 0.96


def _visual_profile(
    *,
    pixel_count: int,
    edge_density: float,
    contrast: float,
    saturation: float,
    transparent_ratio: float,
    unique_color_estimate: int,
    is_blank_like: bool,
) -> str:
    if is_blank_like:
        return "blank_like"
    if transparent_ratio >= 0.18 and pixel_count <= 262144:
        return "transparent_graphic"
    if unique_color_estimate <= 16 and edge_density < 0.04:
        return "flat_graphic"
    if edge_density >= 0.08 and unique_color_estimate >= 512:
        return "photo_like"
    if edge_density >= 0.04 or contrast >= 0.2 or saturation >= 0.3:
        return "detailed_graphic"
    return "low_detail"


def _dict_value(container: dict[str, object], key: str) -> dict[str, object]:
    value = container.get(key)
    return value if isinstance(value, dict) else {}


def _int_value(container: dict[str, object], key: str) -> int:
    value = container.get(key)
    return value if isinstance(value, int) else 0


def _float_value(container: dict[str, object], key: str) -> float:
    value = container.get(key)
    if isinstance(value, int | float):
        return float(value)
    return 0.0


def _round(value: float) -> float:
    return round(float(value), 4)
