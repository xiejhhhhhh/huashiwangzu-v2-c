"""Sandbox contract tests for media-intelligence.

These tests validate the layered placeholder pipeline without framework DB,
uploaded-file records, OpenCV, OCR engines, embedding services, ASR, or VLM keys.
"""

from __future__ import annotations

import asyncio
import struct
import tempfile
import zlib
from pathlib import Path

import pytest
from app.core.exceptions import ValidationError
from media_intelligence_import import load_pipeline, load_router

pipeline = load_pipeline()
router = load_router()


def _write_png(path: Path, width: int = 2, height: int = 3) -> None:
    signature = b"\x89PNG\r\n\x1a\n"
    ihdr_data = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)
    ihdr = _chunk(b"IHDR", ihdr_data)
    raw_row = b"\x00" + (b"\x00\x00\x00" * width)
    image_data = zlib.compress(raw_row * height)
    idat = _chunk(b"IDAT", image_data)
    iend = _chunk(b"IEND", b"")
    path.write_bytes(signature + ihdr + idat + iend)


def _chunk(kind: bytes, data: bytes) -> bytes:
    crc = zlib.crc32(kind + data) & 0xFFFFFFFF
    return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", crc)


def test_analyze_image_contract() -> None:
    with tempfile.TemporaryDirectory() as tmp_dir:
        image_path = Path(tmp_dir) / "sample.png"
        _write_png(image_path)
        result = asyncio.run(
            pipeline.analyze_image_path(
                7,
                "sample.png",
                image_path,
                "png",
                {"include_embedding": True, "refine": True},
            )
        )

    assert result["schema_version"] == "media-intelligence.analysis.v1"
    assert result["media_type"] == "image"
    assert result["source"]["width"] == 2
    assert result["source"]["height"] == 3
    assert result["artifacts"]["embedding"]["dimensions"] == 32
    assert [stage["stage"] for stage in result["stages"]] == [
        "local_algorithms",
        "small_model",
        "vlm_refine",
    ]


def test_extract_keyframes_contract() -> None:
    with tempfile.TemporaryDirectory() as tmp_dir:
        video_path = Path(tmp_dir) / "clip.mp4"
        video_path.write_bytes(b"placeholder-video" * 2048)
        result = asyncio.run(
            pipeline.extract_keyframes_path(
                11,
                "clip.mp4",
                video_path,
                "mp4",
                {"max_keyframes": 3},
            )
        )

    assert result["media_type"] == "video"
    assert 1 <= len(result["artifacts"]["keyframes"]) <= 3
    assert result["artifacts"]["keyframes"][0]["source"] == "placeholder"
    assert result["stages"][0]["provider"] == "local_algorithms.placeholder"


def test_vlm_refine_existing_analysis_contract() -> None:
    analysis = {
        "analysis_id": "a1",
        "source": {
            "file_id": 1,
            "file_name": "sample.png",
            "extension": "png",
            "media_type": "image",
        },
        "stages": [],
        "warnings": [],
        "summary": "local summary",
    }
    result = asyncio.run(pipeline.refine_analysis_result(analysis, "focus on product labels"))
    assert result["schema_version"] == "media-intelligence.analysis.v1"
    assert result["summary"]
    assert result["stages"][-1]["stage"] == "vlm_refine"
    assert result["warnings"]


def test_media_type_resolution() -> None:
    assert pipeline.media_type_for_extension("jpg") == "image"
    assert pipeline.media_type_for_extension(".mp4") == "video"


def test_capability_file_params_reject_invalid_values() -> None:
    with pytest.raises(ValidationError):
        router._file_params({"file_id": 0})
    with pytest.raises(ValidationError):
        router._file_params({"file_id": "abc"})
    with pytest.raises(ValidationError):
        router._file_params({"file_id": 1, "dimensions": 7}, dimensions=True)
    with pytest.raises(ValidationError):
        router._file_params({"file_id": 1, "max_keyframes": 13}, max_keyframes=True)


def test_capability_file_params_normalize_valid_values() -> None:
    result = router._file_params(
        {"file_id": "7", "dimensions": "8", "max_keyframes": "12"},
        dimensions=True,
        max_keyframes=True,
    )

    assert result["file_id"] == 7
    assert result["dimensions"] == 8
    assert result["max_keyframes"] == 12


if __name__ == "__main__":
    test_analyze_image_contract()
    test_extract_keyframes_contract()
    test_vlm_refine_existing_analysis_contract()
    test_media_type_resolution()
    test_capability_file_params_reject_invalid_values()
    test_capability_file_params_normalize_valid_values()
    print("PASS: media-intelligence sandbox contract")
