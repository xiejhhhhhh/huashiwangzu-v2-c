"""Sandbox contract tests for media-intelligence.

These tests validate the local facts pipeline without framework DB,
uploaded-file records, OCR engines, small-model adapters, ASR, or VLM keys.
"""

from __future__ import annotations

import asyncio
import importlib.util
import json
import struct
import sys
import tempfile
import zlib
from pathlib import Path

import pytest

BACKEND_ROOT = Path(__file__).resolve().parents[3] / "backend"
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.core.exceptions import ValidationError
from media_intelligence_import import load_pipeline, load_router

pipeline = load_pipeline()
router = load_router()
local_algorithms = sys.modules["media_intelligence_backend.providers.local_algorithms"]
NORMALIZER_PATH = BACKEND_ROOT / "app" / "services" / "content" / "ir_normalizer.py"


def _load_normalizer():
    spec = importlib.util.spec_from_file_location("content_ir_normalizer", NORMALIZER_PATH)
    if spec is None or spec.loader is None:
        raise RuntimeError("Cannot load ir_normalizer.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


normalizer = _load_normalizer()


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
                {"include_embedding": True, "refine": False},
            )
        )

    normalized_ir = asyncio.run(normalizer.normalize_ir(result))

    assert result["schema_version"] == "1.0"
    assert result["module_schema_version"] == "media-intelligence.analysis.v1"
    assert result["content_type"] == "image"
    assert result["media_type"] == "image"
    assert result["source"]["width"] == 2
    assert result["source"]["height"] == 3
    assert result["source"]["module"] == "media-intelligence"
    assert result["signals"]["metadata"]["format"] == "png"
    assert result["signals"]["metadata"]["mode"] == "RGB"
    assert normalized_ir["blocks"]
    assert normalized_ir["blocks"][0]["type"] == "image"
    assert normalized_ir["blocks"][0]["id"]
    image_ref = normalized_ir["blocks"][0]["data"]["source_ref"]
    assert image_ref["file_id"] == 7
    assert image_ref["filename"] == "sample.png"
    assert image_ref["image"]["width"] == 2
    assert image_ref["image"]["height"] == 3
    assert result["artifacts"]["embedding"]["algorithm"] == "average_intensity_hash"
    assert result["artifacts"]["embedding"]["dimensions"] == 64
    assert [stage["stage"] for stage in result["stages"]] == [
        "local_algorithms",
        "small_model",
    ]
    assert "placeholder" not in json.dumps(result, ensure_ascii=False).lower()


def test_missing_ffprobe_returns_structured_degraded(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(local_algorithms.shutil, "which", lambda _name: None)
    with tempfile.TemporaryDirectory() as tmp_dir:
        video_path = Path(tmp_dir) / "clip.mp4"
        video_path.write_bytes(b"video-bytes" * 2048)
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
    assert result["schema_version"] == "1.0"
    assert result["content_type"] == "mixed"
    assert result["blocks"]
    assert result["blocks"][0]["data"]["source_ref"]["video"]
    assert result["artifacts"]["keyframes"] == []
    assert result["stages"][0]["provider"] == "local_algorithms.local_facts"
    assert result["stages"][0]["status"] == "degraded"
    assert result["blocks"][-1]["data"]["source_ref"]["degraded"] is True
    assert result["degraded"][0]["code"] == "ffprobe_missing"
    assert result["degraded"][0]["dependency"] == "ffprobe"
    assert result["degraded"][0]["install_command"] == "brew install ffmpeg"


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
    normalized_ir = asyncio.run(normalizer.normalize_ir(result))
    assert result["schema_version"] == "1.0"
    assert result["module_schema_version"] == "media-intelligence.analysis.v1"
    assert normalized_ir["blocks"]
    assert normalized_ir["blocks"][0]["data"]["source_ref"]["image"]
    assert result["summary"]
    assert result["stages"][-1]["stage"] == "vlm_refine"
    assert result["model_fallback"]["fallback_used"] is True
    assert result["model_fallback"]["failure_category"] == "not_configured"
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


def test_summarize_existing_analysis_returns_content_ir() -> None:
    result = asyncio.run(
        router._summarize_media(
            {
                "analysis": {
                    "analysis_id": "a2",
                    "source": {"file_id": 9, "file_name": "clip.mp4", "media_type": "video"},
                    "summary": "Transcript summary",
                },
            },
            "user:1",
        )
    )
    normalized_ir = asyncio.run(normalizer.normalize_ir(result))

    assert result["schema_version"] == "1.0"
    assert result["module_schema_version"] == "media-intelligence.summary.v1"
    assert normalized_ir["blocks"]
    assert normalized_ir["blocks"][0]["type"] == "paragraph"
    source_ref = normalized_ir["blocks"][0]["data"]["source_ref"]
    assert source_ref["file_id"] == 9
    assert source_ref["filename"] == "clip.mp4"
    assert source_ref["transcript"]["source"] == "existing_analysis_summary"


if __name__ == "__main__":
    test_analyze_image_contract()
    test_missing_ffprobe_returns_structured_degraded(pytest.MonkeyPatch())
    test_vlm_refine_existing_analysis_contract()
    test_media_type_resolution()
    test_capability_file_params_reject_invalid_values()
    test_capability_file_params_normalize_valid_values()
    test_summarize_existing_analysis_returns_content_ir()
    print("PASS: media-intelligence sandbox contract")
