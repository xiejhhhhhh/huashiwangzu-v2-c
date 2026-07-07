"""Sandbox test for pptx-parser module."""

from __future__ import annotations

import asyncio
import inspect
import importlib.util
import os
import sys
from pathlib import Path
from tempfile import NamedTemporaryFile
from types import ModuleType
from typing import Any, Callable

REPO_ROOT = Path(__file__).resolve().parents[3]
BACKEND_ROOT = REPO_ROOT / "backend"
ROUTER_PATH = REPO_ROOT / "modules" / "pptx-parser" / "backend" / "router.py"
SAMPLE = Path(__file__).resolve().parent / "samples" / "sample.pptx"

if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

os.environ.setdefault("JWT_SECRET", "pptx-parser-sandbox-test-secret")

from app.core.exceptions import ValidationError  # noqa: E402
from app.services.content.ir_normalizer import normalize_ir  # noqa: E402


def load_router() -> ModuleType:
    spec = importlib.util.spec_from_file_location("pptx_parser_router_under_test", ROUTER_PATH)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Unable to load router from {ROUTER_PATH}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


async def parse_with_file(
    router: ModuleType,
    path: Path,
    params: dict[str, Any] | None = None,
) -> dict[str, Any]:
    async def fake_uploaded_file_runner(
        runner_params: dict[str, Any],
        caller: str,
        allowed: set[str],
        parse_file: Callable[[int, object, Path, str], dict[str, Any]],
    ) -> dict[str, Any]:
        assert caller == "user:1"
        assert allowed == {"ppt", "pptx"}
        result = parse_file(runner_params["file_id"], None, path, "pptx")
        if inspect.isawaitable(result):
            return await result
        return result

    async def fake_store_resources(
        result: dict[str, Any],
        *,
        caller: str,
        parser: str,
    ) -> dict[str, Any]:
        assert caller == "user:1"
        assert parser == "pptx-parser"
        return result

    router.run_uploaded_file_capability = fake_uploaded_file_runner
    router.store_extracted_resources_with_diagnostics = fake_store_resources
    return await router._parse(params or {"file_id": 1}, "user:1")


async def validate_success(result: dict[str, Any]) -> None:
    assert result["file_id"] == 1
    assert result["schema_version"] == "content-ir/v1"
    assert result["content_type"] == "presentation"
    assert result["format"] == "pptx"
    assert result["source"]["module"] == "pptx-parser"
    assert result["source_file_id"] == result["file_id"]
    assert result["blocks"], "sample.pptx should produce content blocks"
    assert "resources" in result
    assert "resource_diagnostics" in result

    for block in result["blocks"]:
        assert block["type"] == "slide"
        assert set(("type", "text", "page", "resource_ref", "source_ref", "children")).issubset(block)
        assert isinstance(block["page"], int)
        assert block["source_ref"]["slide"] == block["page"]
        assert block["children"]
        for child in block["children"]:
            assert set(("type", "text", "page", "resource_ref", "source_ref")).issubset(child)
            assert child["type"] in {"heading", "paragraph", "table", "image"}
            assert child["source_ref"]["module"] == "pptx-parser"
            assert child["source_ref"]["slide"] == block["page"]
    for resource in result["resources"]:
        assert resource["resource_type"] == "image"
        assert resource["source_ref"]["slide"] >= 1

    normalized = await normalize_ir(result)
    assert normalized["schema_version"] == "content-ir/v1"
    assert normalized["blocks"]

    print(
        "  Validation PASS (%d blocks, %d resources)"
        % (len(result["blocks"]), len(result["resources"]))
    )


async def validate_bad_inputs(router: ModuleType) -> None:
    try:
        await parse_with_file(router, SAMPLE, {"file_id": 0})
    except ValidationError:
        pass
    else:
        raise AssertionError("non-positive file_id should raise ValidationError")

    with NamedTemporaryFile(suffix=".pptx") as invalid_pptx:
        invalid_path = Path(invalid_pptx.name)
        invalid_path.write_bytes(b"not a pptx archive")
        try:
            await parse_with_file(router, invalid_path)
        except ValidationError:
            pass
        else:
            raise AssertionError("invalid PPTX bytes should raise ValidationError")

    print("  Bad input validation PASS")


async def run_sandbox_contract() -> None:
    if not SAMPLE.exists():
        raise FileNotFoundError(f"sample.pptx not found: {SAMPLE}")

    print("=" * 60)
    print("pptx-parser sandbox test")
    print("=" * 60)

    router = load_router()
    result = await parse_with_file(router, SAMPLE)
    for block in result["blocks"][:8]:
        print("    [%s] slide=%s %s" % (block["type"], block["page"], block["text"][:70]))
    await validate_success(result)
    await validate_bad_inputs(router)
    print("PASS: pptx-parser sandbox test")


def main() -> None:
    asyncio.run(run_sandbox_contract())


def test_sandbox_contract() -> None:
    asyncio.run(run_sandbox_contract())


if __name__ == "__main__":
    main()
