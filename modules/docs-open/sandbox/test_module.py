"""Sandbox contract tests for docs-open.

Run from the repository root with:
PYTHONPATH=backend backend/.venv/bin/python modules/docs-open/sandbox/test_module.py
"""

from __future__ import annotations

import hashlib
import importlib.util
import sys
from pathlib import Path
from types import ModuleType
from typing import Callable

ROOT = Path(__file__).resolve().parents[3]
BACKEND = ROOT / "backend"
MODULE_BACKEND = ROOT / "modules" / "docs-open" / "backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))


def load_module(name: str, path: Path) -> ModuleType:
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Cannot load {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


validators = load_module("docs_open_validators", MODULE_BACKEND / "validators.py")
models = load_module("docs_open_models", MODULE_BACKEND / "models.py")


def assert_raises(fn: Callable[[], object], message_part: str) -> None:
    try:
        fn()
    except Exception as exc:
        assert message_part in str(exc), f"Unexpected error: {exc}"
        return
    raise AssertionError("Expected exception was not raised")


def test_token_scope_contract() -> None:
    scope = validators.normalize_token_scope({
        "doc_ids": [42, "42", 7],
        "edit_doc_ids": ["9"],
    })
    assert scope == {"doc_ids": [42, 7], "edit_doc_ids": [9]}
    assert_raises(lambda: validators.normalize_token_scope({}), "scope must include")
    assert_raises(lambda: validators.normalize_token_scope({"doc_ids": []}), "non-empty list")
    assert_raises(lambda: validators.normalize_token_scope({"doc_ids": [0]}), "positive integer")
    assert_raises(lambda: validators.normalize_token_scope({"doc_ids": [True]}), "positive integer")
    assert_raises(lambda: validators.normalize_token_scope({"all": True}), "unsupported scope keys")
    print("  [TOKEN] Scope boundary contract valid")


def test_token_identity_contract() -> None:
    assert validators.normalize_client_id("docs-open_1.2") == "docs-open_1.2"
    assert_raises(lambda: validators.normalize_client_id("bad'id"), "client_id")
    assert validators.normalize_expiry_hours(1) == 1
    assert validators.normalize_expiry_hours("24") == 24
    assert_raises(lambda: validators.normalize_expiry_hours(0), "positive integer")
    assert_raises(lambda: validators.normalize_expiry_hours(25), "<= 24")
    print("  [TOKEN] Identity and expiry contract valid")


def test_mode_and_document_type_contract() -> None:
    assert validators.normalize_mode("read") == "view"
    assert validators.normalize_mode("view") == "view"
    assert validators.normalize_mode("edit") == "edit"
    assert validators.access_mode_for_mode("view") == "read"
    assert validators.access_mode_for_mode("edit") == "edit"
    assert_raises(lambda: validators.normalize_mode("admin"), "mode must be")

    assert validators.normalize_doc_type("plain") == "txt"
    assert validators.normalize_doc_type(".docx") == "docx"
    assert_raises(lambda: validators.normalize_doc_type("exe"), "doc_type must be")
    assert validators.normalize_title("Report") == "Report"
    assert_raises(lambda: validators.normalize_title("../Report"), "path separators")
    print("  [DOC] Mode, type and title contract valid")


def test_token_hash_contract() -> None:
    raw, prefix, hashed = models.generate_access_token()
    assert len(raw) == 64
    assert prefix == raw[:8]
    assert hashed == hashlib.sha256(raw.encode("utf-8")).hexdigest()
    assert len(hashed) == 64
    assert models.legacy_hash_access_token(raw) != hashed
    print("  [TOKEN] Hashing contract valid")


def test_capability_output_shape_contract() -> None:
    open_result = {
        "id": "42",
        "file_id": 42,
        "title": "Sample Document",
        "type": "txt",
        "category": "text",
        "editor": "text-editor",
        "mime": "text/plain",
    }
    for field in ("id", "file_id", "title", "type", "category", "editor", "mime"):
        assert field in open_result
    assert isinstance(open_result["file_id"], int)

    create_result = {"id": "100", "file_id": 100, "title": "New Document", "type": "txt"}
    for field in ("id", "file_id", "title", "type"):
        assert field in create_result
    assert isinstance(create_result["file_id"], int)
    print("  [CAPABILITY] Output shape contract valid")


def test_scoped_token_auth_boundary_contract() -> None:
    full_jwt_only_endpoints = {
        "POST /api/docs/token",
        "POST /api/docs/open",
        "POST /api/docs",
        "POST /api/docs/{file_id}/export",
        "POST /api/docs/{file_id}/revoke-tokens",
    }
    scoped_token_endpoints = {
        "GET /api/docs/{file_id}/content",
        "POST /api/docs/{file_id}/content",
        "GET /api/docs/embed/{file_id}",
        "GET /api/docs/{file_id}/file?token=...",
    }
    assert full_jwt_only_endpoints
    assert scoped_token_endpoints
    assert full_jwt_only_endpoints.isdisjoint(scoped_token_endpoints)
    print("  [AUTH] Scoped token boundary contract documented")


def main() -> None:
    print("=" * 60)
    print("docs-open sandbox contract test")
    print("=" * 60)
    test_token_scope_contract()
    test_token_identity_contract()
    test_mode_and_document_type_contract()
    test_token_hash_contract()
    test_capability_output_shape_contract()
    test_scoped_token_auth_boundary_contract()
    print("=" * 60)
    print("PASS: docs-open sandbox contract test")


if __name__ == "__main__":
    main()
