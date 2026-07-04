"""Sandbox test for pdf-parser module.

Validates that a real PDF sample produces non-empty unified content blocks.
Usage: ../../../backend/.venv/bin/python test_module.py  (from modules/pdf-parser/sandbox/)
"""
import asyncio
import importlib.util
import os
import sys
from pathlib import Path
from types import ModuleType
from typing import Any, Callable

SAMPLE = Path(__file__).resolve().parent / "samples" / "sample.pdf"
REPO_ROOT = Path(__file__).resolve().parents[3]
BACKEND_ROOT = REPO_ROOT / "backend"
ROUTER_PATH = REPO_ROOT / "modules" / "pdf-parser" / "backend" / "router.py"

if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

os.environ.setdefault("JWT_SECRET", "pdf-parser-sandbox-test-secret")

from app.services.content.ir_normalizer import normalize_ir  # noqa: E402


def load_router() -> ModuleType:
    spec = importlib.util.spec_from_file_location("pdf_parser_router_under_test", ROUTER_PATH)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Unable to load router from {ROUTER_PATH}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


async def parse_pdf(path: Path, params: dict[str, Any] | None = None) -> dict[str, Any]:
    router = load_router()

    async def fake_uploaded_file_runner(
        runner_params: dict[str, Any],
        caller: str,
        allowed: set[str],
        parse_file: Callable[[int, object, Path, str], dict[str, Any]],
    ) -> dict[str, Any]:
        assert caller == "user:1"
        assert allowed == {"pdf"}
        return parse_file(runner_params["file_id"], None, path, "pdf")

    async def fake_store_resources(
        result: dict[str, Any],
        *,
        caller: str,
        parser: str,
    ) -> dict[str, Any]:
        assert caller == "user:1"
        assert parser == "pdf-parser"
        return result

    router.run_uploaded_file_capability = fake_uploaded_file_runner
    router.store_extracted_resources_with_diagnostics = fake_store_resources
    return await router._parse(params or {"file_id": 1}, "user:1")


def validate(result: dict[str, Any]) -> None:
    assert isinstance(result, dict) and all(k in result for k in ("file_id", "format", "blocks", "resources"))
    assert result["schema_version"] == "content-ir/v1"
    assert result["content_type"] == "document"
    assert result["format"] == "pdf"
    assert result["source"]["module"] == "pdf-parser"
    assert result["source_file_id"] == result["file_id"]
    assert isinstance(result["metadata"], dict)
    assert isinstance(result["warnings"], list)
    blocks = result["blocks"]
    resources = result["resources"]
    assert isinstance(blocks, list)
    assert isinstance(resources, list)
    assert blocks or resources, "Expected the sample PDF to produce content blocks or resources"
    assert any(block.get("text", "").strip() for block in blocks), "Expected sample PDF text extraction to be non-empty"
    for block in blocks:
        assert isinstance(block, dict)
        assert all(key in block for key in ("type", "text", "page", "resource_ref", "source_ref"))
        assert block["type"] in ("heading", "paragraph", "table", "image")
        assert isinstance(block["page"], int) and block["page"] >= 1
        assert block["source_ref"]["module"] == "pdf-parser"
        assert block["source_ref"]["file_id"] == result["file_id"]
        assert isinstance(block["source_ref"]["page"], int)
    for resource in resources:
        assert isinstance(resource, dict)
        assert all(key in resource for key in ("id", "type", "resource_type", "page", "mime_type", "filename", "description", "source_ref"))
        assert isinstance(resource["page"], int) and resource["page"] >= 1
    normalized = asyncio.run(normalize_ir(result))
    assert normalized["schema_version"] == "content-ir/v1"
    assert normalized["blocks"]
    print("  Validation PASS (%d blocks, %d resources)" % (len(result["blocks"]), len(result["resources"])))


def test_sample_pdf_parses_real_content() -> None:
    assert SAMPLE.exists(), f"Sample not found: {SAMPLE}"
    result = asyncio.run(parse_pdf(SAMPLE))
    validate(result)


def test_empty_parse_result_is_rejected() -> None:
    empty = {
        "schema_version": "content-ir/v1",
        "content_type": "document",
        "file_id": 0,
        "format": "pdf",
        "source_file_id": 0,
        "source": {"module": "pdf-parser"},
        "metadata": {},
        "warnings": [],
        "blocks": [],
        "resources": [],
    }
    try:
        validate(empty)
    except AssertionError as exc:
        assert "Expected the sample PDF" in str(exc)
    else:
        raise AssertionError("Empty parse result should not pass sandbox validation")


def main() -> None:
    print("=" * 60)
    print("pdf-parser sandbox test")
    print("=" * 60)
    assert SAMPLE.exists(), f"Sample not found: {SAMPLE}"
    result = asyncio.run(parse_pdf(SAMPLE))
    print("\nParsed content:")
    for block in result["blocks"]:
        print("    [%s] p=%s text=%s" % (block["type"], block["page"], block["text"][:70]))
    print("\nResources:")
    for resource in result["resources"]:
        print("    [%s] %s" % (resource["type"], resource["description"][:70]))
    validate(result)
    test_empty_parse_result_is_rejected()
    print("\nPASS: pdf-parser sandbox test")


if __name__ == "__main__":
    main()
