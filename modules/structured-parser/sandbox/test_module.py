"""Sandbox test for structured-parser module.

Validates production JSON/YAML parsing into unified content blocks.
"""
import asyncio
import json
import os
import sys
import tempfile
from pathlib import Path

SDIR = Path(__file__).resolve().parent / "samples"
MODULE_DIR = Path(__file__).resolve().parents[1]
BACKEND_DIR = MODULE_DIR / "backend"
REPO_BACKEND_DIR = Path(__file__).resolve().parents[3] / "backend"
sys.path.insert(0, str(REPO_BACKEND_DIR))
sys.path.insert(0, str(MODULE_DIR))
sys.path.insert(0, str(BACKEND_DIR))

os.environ.setdefault("JWT_SECRET", "structured-parser-sandbox-secret")

from app.core.exceptions import ValidationError  # noqa: E402
from backend.router import _parse as router_parse  # noqa: E402
from parser import (  # noqa: E402
    MAX_STRUCTURED_BYTES,
    StructuredFileTooLargeError,
    StructuredParseError,
    parse_structured_content,
    parse_structured_file,
)


def validate_shape(result: dict[str, object], label: str) -> None:
    assert all(key in result for key in ("file_id", "format", "blocks", "resources"))
    blocks = result["blocks"]
    resources = result["resources"]
    assert isinstance(blocks, list)
    assert isinstance(resources, list)
    for block in blocks:
        assert isinstance(block, dict)
        assert all(key in block for key in ("type", "text", "page", "resource_ref"))
        assert block["type"] in {"paragraph"}
    print(f"  [{label}] Validation PASS ({len(blocks)} blocks)")


def test_sample_json() -> None:
    sample = SDIR / "sample.json"
    assert sample.exists(), f"Sample not found: {sample}"
    result = parse_structured_file(1, sample, "json")
    validate_shape(result, "sample.json")
    texts = [str(block["text"]) for block in result["blocks"]]
    assert result["format"] == "json"
    assert any("结构化数据：3 个字段" in text for text in texts)
    assert any("name: \"sample\"" in text for text in texts)
    assert any("items[0].label: \"alpha\"" in text for text in texts)


def test_sample_yaml() -> None:
    sample = SDIR / "sample.yaml"
    assert sample.exists(), f"Sample not found: {sample}"
    result = parse_structured_file(2, sample, "yaml")
    validate_shape(result, "sample.yaml")
    texts = [str(block["text"]) for block in result["blocks"]]
    assert result["format"] == "yaml"
    assert any("project.name: \"structured-parser\"" in text for text in texts)
    assert any("enabled: true" in text for text in texts)


def test_empty_file_returns_explicit_empty_block() -> None:
    result = parse_structured_content("   \n", 3, "json")
    validate_shape(result, "empty.json")
    assert result["blocks"][0]["text"] == "空结构化文件：0 个字段"
    assert result["metadata"]["empty_file"] is True


def test_empty_object_returns_zero_field_summary() -> None:
    result = parse_structured_content("{}", 4, "json")
    validate_shape(result, "empty-object.json")
    assert result["blocks"][0]["text"] == "结构化数据：0 个字段"
    assert result["metadata"]["field_count"] == 0


def test_root_scalar_has_stable_path() -> None:
    result = parse_structured_content("123", 5, "json")
    validate_shape(result, "scalar.json")
    assert result["blocks"][1]["text"] == "$: 123"


def test_gbk_json_decodes() -> None:
    with tempfile.TemporaryDirectory(prefix="structured-parser-sandbox-") as tmp:
        path = Path(tmp) / "gbk.json"
        payload = json.dumps({"name": "中文"}, ensure_ascii=False).encode("gbk")
        path.write_bytes(payload)
        result = parse_structured_file(6, path, "json")
    validate_shape(result, "gbk.json")
    assert "name: \"中文\"" in result["blocks"][1]["text"]


def test_invalid_json_raises() -> None:
    try:
        parse_structured_content("{broken", 7, "json")
    except StructuredParseError:
        return
    raise AssertionError("invalid JSON must raise instead of returning fake success")


def test_invalid_yaml_raises() -> None:
    try:
        parse_structured_content("name: [unterminated", 8, "yaml")
    except StructuredParseError:
        return
    raise AssertionError("invalid YAML must raise instead of returning fake success")


def test_large_file_raises_before_parse() -> None:
    with tempfile.TemporaryDirectory(prefix="structured-parser-sandbox-") as tmp:
        path = Path(tmp) / "large.json"
        path.write_bytes(b" " * (MAX_STRUCTURED_BYTES + 1))
        try:
            parse_structured_file(9, path, "json")
        except StructuredFileTooLargeError:
            return
    raise AssertionError("oversized structured file must raise before parsing")


def test_bad_file_id_maps_to_validation_error() -> None:
    try:
        asyncio.run(router_parse({"file_id": "bad"}, "user:1"))
    except ValidationError as exc:
        assert "positive integer" in exc.message
        return
    raise AssertionError("bad file_id must raise structured validation error")


def main() -> None:
    print("=" * 60)
    print("structured-parser sandbox test")
    print("=" * 60)
    test_sample_json()
    test_sample_yaml()
    test_empty_file_returns_explicit_empty_block()
    test_empty_object_returns_zero_field_summary()
    test_root_scalar_has_stable_path()
    test_gbk_json_decodes()
    test_invalid_json_raises()
    test_invalid_yaml_raises()
    test_large_file_raises_before_parse()
    test_bad_file_id_maps_to_validation_error()
    print("PASS: structured-parser sandbox test")


if __name__ == "__main__":
    main()
