"""Sandbox test for markdown-parser production parser."""
import importlib.util
import os
import sys
from pathlib import Path
from types import ModuleType
from typing import Any

MODULE_DIR = Path(__file__).resolve().parents[1]
REPO_ROOT = MODULE_DIR.parents[1]
BACKEND_DIR = REPO_ROOT / "backend"
SAMPLE_DIR = Path(__file__).resolve().parent / "samples"


def load_router_module() -> ModuleType:
    os.environ.setdefault("JWT_SECRET", "markdown-parser-sandbox-test-secret")

    backend_path = str(BACKEND_DIR)
    if backend_path not in sys.path:
        sys.path.insert(0, backend_path)

    router_path = MODULE_DIR / "backend" / "router.py"
    spec = importlib.util.spec_from_file_location("markdown_parser_router", router_path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Cannot load router module from {router_path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def validate(result: dict[str, Any], label: str) -> None:
    assert set(result) == {"file_id", "format", "blocks", "resources"}
    blocks = result["blocks"]
    resources = result["resources"]
    assert isinstance(blocks, list)
    assert isinstance(resources, list)
    for block in blocks:
        assert isinstance(block, dict)
        assert set(block) == {"type", "text", "page", "resource_ref"}
    for resource in resources:
        assert isinstance(resource, dict)
        assert set(resource) == {"id", "type", "file_storage_id", "text_desc"}
    print(f"  [{label}] Validation PASS ({len(blocks)} blocks, {len(resources)} resources)")


def test_invalid_file_ids() -> None:
    router = load_router_module()
    for bad_file_id in (0, -1, "abc", True, None):
        try:
            router._require_file_id({"file_id": bad_file_id})
        except router.ValidationError:
            pass
        else:
            raise AssertionError(f"Expected ValidationError for file_id={bad_file_id!r}")


def test_parse_sample() -> None:
    sample = SAMPLE_DIR / "sample.md"
    assert sample.exists(), f"Sample not found: {sample}"

    router = load_router_module()
    result = router.parse_markdown_content(sample.read_text(encoding="utf-8"), file_id=1)
    validate(result, "sample.md")

    blocks = result["blocks"]
    assert result["format"] == "markdown"
    assert any(block["type"] == "heading" for block in blocks), "Expected heading block"
    assert any(block["type"] == "paragraph" for block in blocks), "Expected paragraph block"
    assert any(block["type"] == "list" for block in blocks), "Expected list block"
    assert any(block["type"] == "code" and "not a heading" in block["text"] for block in blocks), "Expected fenced code block"
    assert any(block["type"] == "table" and "Name" in block["text"] for block in blocks), "Expected table block"
    assert any(block["type"] == "image" and block["resource_ref"] == 1 for block in blocks), "Expected image block"
    assert len(result["resources"]) == 1
    assert not any(block["type"] == "paragraph" and block["text"].startswith("![") for block in blocks)

    code_block = next(block for block in blocks if block["type"] == "code")
    assert "```" not in code_block["text"], "Code block should not include fence markers"
    assert any(block["text"] == "After code." for block in blocks), "Expected text after code fence"


def main() -> None:
    print("=" * 60)
    print("markdown-parser sandbox test")
    print("=" * 60)
    test_invalid_file_ids()
    test_parse_sample()
    print("PASS: markdown-parser sandbox test")


if __name__ == "__main__":
    main()
