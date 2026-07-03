"""Sandbox validation for the image-vision local-first analysis path."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

from PIL import Image

MODULE_ROOT = Path(__file__).resolve().parents[1]
SAMPLE = Path(__file__).resolve().parent / "samples" / "sample.png"
ANALYZER_PATH = MODULE_ROOT / "backend" / "image_analysis.py"


def _load_analyzer():
    spec = importlib.util.spec_from_file_location("image_vision_local_analysis", ANALYZER_PATH)
    if spec is None or spec.loader is None:
        raise RuntimeError("Cannot load image_analysis.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_local_analysis_contract() -> None:
    analyzer = _load_analyzer()
    raw = SAMPLE.read_bytes()
    result = analyzer.analyze_image_bytes(raw, SAMPLE.name, "png")
    summary = analyzer.build_local_summary(result)

    assert result["analyzer"] == "pillow-local-v1"
    assert result["format"] in {"PNG", "png"}
    assert result["dimensions"]["width"] > 0
    assert result["dimensions"]["height"] > 0
    assert result["color"]["dominant_colors"]
    assert result["hashes"]["average_hash"]
    assert "本地图片分析" in summary


def test_vlm_decision_skips_blank_image() -> None:
    analyzer = _load_analyzer()
    blank = Image.new("RGBA", (64, 64), (255, 255, 255, 255))
    temp = MODULE_ROOT / "sandbox" / "samples" / ".image_vision_blank_tmp.png"
    try:
        blank.save(temp)
        result = analyzer.analyze_image_bytes(temp.read_bytes(), temp.name, "png")
        decision = analyzer.should_use_vlm(result, "auto")
    finally:
        if temp.exists():
            temp.unlink()

    assert result["quality"]["is_blank_like"] is True
    assert decision["use_vlm"] is False
    assert "blank" in decision["reason"]


def main() -> None:
    if not SAMPLE.exists():
        print("ERROR: sample.png not found")
        raise SystemExit(1)

    print("=" * 60)
    print("image-vision sandbox test")
    print("=" * 60)
    test_local_analysis_contract()
    print("  Local analysis contract PASS")
    test_vlm_decision_skips_blank_image()
    print("  VLM auto-skip decision PASS")
    print("PASS: image-vision sandbox test")


if __name__ == "__main__":
    main()
