from __future__ import annotations

import hashlib
import re
from pathlib import Path
from typing import Any

from .base import MediaContext, MediaProvider, StageResult


class LocalAlgorithmProvider(MediaProvider):
    provider_key = "local_algorithms.placeholder"

    async def run(self, context: MediaContext) -> StageResult:
        action = str(context.options.get("action", "analyze"))
        data: dict[str, Any] = {
            "metadata": _metadata(context),
        }

        if action in {"analyze_image", "analyze_video", "extract_keyframes"}:
            if context.media_type == "video":
                data["keyframes"] = _placeholder_keyframes(context)
        if action in {"analyze_image", "analyze_video", "ocr"}:
            data["ocr"] = _placeholder_ocr(context)
        if action in {"analyze_image", "analyze_video", "detect_objects"}:
            data["objects"] = _placeholder_objects(context)
        if action in {"analyze_image", "embed_image"} and context.media_type == "image":
            data["embedding"] = _deterministic_embedding(context)

        return StageResult(
            stage="local_algorithms",
            provider=self.provider_key,
            status="placeholder",
            data=data,
            warnings=[
                "OpenCV/Pillow/OCR/object-detection providers are not wired yet; deterministic local placeholders are active."
            ],
            confidence=0.35,
        )


def _metadata(context: MediaContext) -> dict[str, Any]:
    metadata: dict[str, Any] = {
        "file_id": context.file_id,
        "file_name": context.file_name,
        "extension": context.extension,
        "media_type": context.media_type,
        "size_bytes": context.size_bytes,
        "head_sha256": context.head_sha256,
    }
    if context.media_type == "image":
        dimensions = _read_image_dimensions(context.path)
        if dimensions is not None:
            metadata["width"] = dimensions[0]
            metadata["height"] = dimensions[1]
    return metadata


def _read_image_dimensions(path: Path) -> tuple[int, int] | None:
    try:
        header = path.read_bytes()[:65536]
    except OSError:
        return None
    if header.startswith(b"\x89PNG\r\n\x1a\n") and len(header) >= 24:
        return int.from_bytes(header[16:20], "big"), int.from_bytes(header[20:24], "big")
    if header.startswith(b"\xff\xd8"):
        return _read_jpeg_dimensions(header)
    if header.startswith(b"GIF87a") or header.startswith(b"GIF89a"):
        if len(header) >= 10:
            return int.from_bytes(header[6:8], "little"), int.from_bytes(header[8:10], "little")
    return None


def _read_jpeg_dimensions(header: bytes) -> tuple[int, int] | None:
    idx = 2
    while idx + 9 < len(header):
        if header[idx] != 0xFF:
            idx += 1
            continue
        marker = header[idx + 1]
        idx += 2
        if marker in {0xD8, 0xD9, 0x01}:
            continue
        if idx + 2 > len(header):
            return None
        segment_len = int.from_bytes(header[idx:idx + 2], "big")
        if segment_len < 2 or idx + segment_len > len(header):
            return None
        if marker in {0xC0, 0xC1, 0xC2, 0xC3, 0xC5, 0xC6, 0xC7, 0xC9, 0xCA, 0xCB, 0xCD, 0xCE, 0xCF}:
            height = int.from_bytes(header[idx + 3:idx + 5], "big")
            width = int.from_bytes(header[idx + 5:idx + 7], "big")
            return width, height
        idx += segment_len
    return None


def _placeholder_keyframes(context: MediaContext) -> list[dict[str, Any]]:
    max_keyframes = _bounded_int(context.options.get("max_keyframes"), 5, 1, 12)
    count = max(1, min(max_keyframes, 1 + context.size_bytes // 10_000_000))
    return [
        {
            "index": idx,
            "timestamp_seconds": round(idx * 2.5, 2),
            "source": "placeholder",
            "description": f"Placeholder keyframe {idx + 1} for {context.file_name}",
        }
        for idx in range(count)
    ]


def _placeholder_ocr(context: MediaContext) -> dict[str, Any]:
    return {
        "engine": "not_configured",
        "text": "",
        "regions": [],
        "language": None,
        "status": "placeholder",
        "note": "Wire PaddleOCR/Tesseract/vision OCR provider here.",
    }


def _placeholder_objects(context: MediaContext) -> list[dict[str, Any]]:
    tokens = [
        token.lower()
        for token in re.split(r"[^A-Za-z0-9]+", Path(context.file_name).stem)
        if len(token) >= 3
    ]
    label = tokens[0] if tokens else context.media_type
    return [
        {
            "label": label,
            "confidence": 0.2,
            "box": None,
            "source": "filename_hint",
        }
    ]


def _deterministic_embedding(context: MediaContext) -> dict[str, Any]:
    dimensions = _bounded_int(context.options.get("dimensions"), 32, 8, 1024)
    seed = hashlib.sha256(f"{context.file_id}:{context.head_sha256}:{context.size_bytes}".encode("utf-8")).digest()
    values: list[float] = []
    while len(values) < dimensions:
        for byte in seed:
            values.append(round((byte / 127.5) - 1.0, 6))
            if len(values) >= dimensions:
                break
        seed = hashlib.sha256(seed).digest()
    return {
        "model": "deterministic-placeholder",
        "dimensions": dimensions,
        "vector": values,
    }


def _bounded_int(value: object, default: int, minimum: int, maximum: int) -> int:
    try:
        parsed = int(value) if value is not None else default
    except (TypeError, ValueError):
        parsed = default
    return max(minimum, min(maximum, parsed))
