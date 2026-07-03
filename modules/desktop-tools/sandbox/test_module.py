"""Sandbox contract test for the desktop-tools module.

This module is a bridge over framework file/app services, so the sandbox test
imports the real router and validates its public capability contract without
creating framework data.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
BACKEND_ROOT = REPO_ROOT / "backend"
MODULE_BACKEND = REPO_ROOT / "modules" / "desktop-tools" / "backend"
sys.path.insert(0, str(BACKEND_ROOT))
sys.path.insert(0, str(MODULE_BACKEND))
os.environ.setdefault("JWT_SECRET", "desktop-tools-sandbox-only-secret")

from app.core.exceptions import ValidationError  # noqa: E402
from app.services.module_registry import list_capabilities  # noqa: E402
from router import (  # noqa: E402
    _EXT_PARSER_MAP,
    _TEXT_EXTS,
    MAX_PAGE_SIZE,
    MAX_READ_BLOCKS,
    MAX_READ_CHARS,
    _coerce_page_size,
    _limit_blocks,
    _normalize_extension,
    _normalize_file_name,
    _truncate_text,
)

EXPECTED_ACTIONS = {
    "list_files",
    "search_files",
    "read_file",
    "list_apps",
    "get_file",
    "create_file",
    "replace_file",
    "delete_file",
    "rename_file",
    "copy_file",
    "list_versions",
    "restore_version",
    "replace_file_from_artifact",
    "publish_artifact",
    "refresh",
}

EXPECTED_PARSER_MAP = {
    "pdf": "pdf-parser",
    "docx": "docx-parser",
    "xlsx": "xlsx-parser",
    "xls": "xlsx-parser",
    "csv": "xlsx-parser",
    "pptx": "pptx-parser",
    "txt": "text-parser",
    "md": "text-parser",
    "markdown": "text-parser",
    "text": "text-parser",
    "log": "text-parser",
}


def _expect_validation_error(fn, message: str) -> None:
    try:
        fn()
    except ValidationError:
        return
    raise AssertionError(message)


def test_registered_capabilities() -> None:
    """Importing the router registers every public action."""
    capabilities = list_capabilities(role="admin", caller="user:1")
    actions = {
        cap["action"]
        for cap in capabilities
        if cap["module"] == "desktop-tools"
    }
    assert actions == EXPECTED_ACTIONS, actions
    print(f"  [CAPABILITIES] {len(actions)} desktop-tools actions registered: OK")


def test_parser_map_completeness() -> None:
    """Every delegated parser mapping stays in sync with the router."""
    assert _EXT_PARSER_MAP == EXPECTED_PARSER_MAP
    for ext in ("txt", "md", "json", "yaml", "csv"):
        assert ext in _TEXT_EXTS
    print(f"  [PARSER MAP] {len(_EXT_PARSER_MAP)} parser mappings: OK")


def test_input_guards() -> None:
    """Path-like names/extensions and oversize pages fail before service calls."""
    assert _normalize_extension(".TXT") == "txt"
    assert _normalize_file_name(" report ") == "report"
    assert _coerce_page_size(MAX_PAGE_SIZE) == MAX_PAGE_SIZE

    _expect_validation_error(
        lambda: _normalize_extension("../txt"),
        "path-like extension should be rejected",
    )
    _expect_validation_error(
        lambda: _normalize_file_name("../report"),
        "path-like file name should be rejected",
    )
    _expect_validation_error(
        lambda: _coerce_page_size(MAX_PAGE_SIZE + 1),
        "oversized page_size should be rejected",
    )
    print("  [GUARDS] path and pagination guards: OK")


def test_output_truncation() -> None:
    """Read output is capped and reports truncation metadata."""
    text, info = _truncate_text("a" * (MAX_READ_CHARS + 5))
    assert len(text) == MAX_READ_CHARS
    assert info["truncated"] is True

    blocks = [
        {"type": "paragraph", "text": "x" * 500}
        for _ in range(MAX_READ_BLOCKS + 5)
    ]
    limited, block_info = _limit_blocks(blocks, max_chars=1000)
    assert len(limited) <= MAX_READ_BLOCKS
    assert block_info["returned_chars"] <= 1000
    assert block_info["truncated"] is True
    print("  [TRUNCATION] content and block limits: OK")


def main() -> None:
    print("=" * 60)
    print("desktop-tools sandbox contract test")
    print("=" * 60)

    test_registered_capabilities()
    test_parser_map_completeness()
    test_input_guards()
    test_output_truncation()

    print("=" * 60)
    print("PASS: desktop-tools sandbox contract test")


if __name__ == "__main__":
    main()
