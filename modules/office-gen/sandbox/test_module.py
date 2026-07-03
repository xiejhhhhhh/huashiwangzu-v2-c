"""Sandbox validation for office-gen.

Runs without DB writes: loads the module generator directly and verifies that
docx/xlsx/pptx/pdf outputs are real files, including Content IR-style English
blocks used by the framework export pipeline.
"""
from __future__ import annotations

import importlib.util
import io
import sys
import types
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[3]


def _load_backend_module(name: str) -> types.ModuleType:
    full_name = f"office_gen_sandbox.{name}"
    file_path = PROJECT_ROOT / "modules" / "office-gen" / "backend" / f"{name}.py"
    spec = importlib.util.spec_from_file_location(full_name, file_path)
    if not spec or not spec.loader:
        raise RuntimeError(f"Cannot load module: {file_path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[full_name] = module
    spec.loader.exec_module(module)
    return module


gen = _load_backend_module("generator")


def _assert_docx(data: bytes) -> None:
    from docx import Document

    assert len(data) > 100
    doc = Document(io.BytesIO(data))
    text = "\n".join(p.text for p in doc.paragraphs)
    assert "Content IR Title" in text
    assert "Content IR paragraph" in text


def _assert_xlsx(data: bytes) -> None:
    from openpyxl import load_workbook

    assert len(data) > 100
    wb = load_workbook(io.BytesIO(data))
    ws = wb["Sheet1"]
    assert ws["A1"].value == "item"
    assert ws["B2"].value == "0"


def _assert_pptx(data: bytes) -> None:
    from pptx import Presentation

    assert len(data) > 100
    prs = Presentation(io.BytesIO(data))
    assert prs.slides[0].shapes.title.text == "Content IR Slide"
    slide_text = "\n".join(shape.text for shape in prs.slides[0].shapes if hasattr(shape, "text"))
    assert "First point" in slide_text


def _assert_pdf(data: bytes) -> None:
    assert len(data) > 500
    assert data.startswith(b"%PDF")
    assert data.rstrip().endswith(b"%%EOF")


def test_docx_generation_accepts_content_ir_blocks() -> None:
    data = gen.generate_docx({
        "filename": "sandbox_doc",
        "content": [
            {"type": "heading", "text": "Content IR Title", "data": {"level": 1}},
            {"type": "paragraph", "text": "Content IR paragraph"},
            {"type": "table", "header": ["item", "count"], "rows": [["Alpha", 0]]},
        ],
    })
    _assert_docx(data)


def test_xlsx_generation_accepts_content_ir_tables() -> None:
    data = gen.generate_xlsx({
        "filename": "sandbox_sheet",
        "content_ir": {
            "content_type": "spreadsheet",
            "blocks": [{
                "type": "sheet",
                "data": {"name": "Sheet1"},
                "children": [{
                    "type": "table",
                    "data": {
                        "headers": [{"name": "item"}, {"name": "count"}],
                        "rows": [{"item": "Alpha", "count": 0}],
                    },
                }],
            }],
        },
    })
    _assert_xlsx(data)


def test_pptx_generation_accepts_content_ir_elements() -> None:
    data = gen.generate_pptx({
        "filename": "sandbox_deck",
        "content_ir": {
            "content_type": "presentation",
            "blocks": [{
                "type": "slide",
                "data": {"title": "Content IR Slide"},
                "children": [
                    {"type": "heading", "text": "First point"},
                    {"type": "paragraph", "text": "Second point", "level": 1},
                ],
            }],
        },
    })
    _assert_pptx(data)


def test_pdf_generation_accepts_content_ir_blocks() -> None:
    data = gen.generate_pdf({
        "filename": "sandbox_pdf",
        "blocks": [
            {"type": "heading", "data": {"text": "PDF Title", "level": 1}},
            {"type": "paragraph", "data": {"text": "PDF paragraph"}},
            {"type": "table", "data": {"headers": ["item", "count"], "rows": [{"item": "Alpha", "count": 0}]}},
        ],
    })
    _assert_pdf(data)


def test_generators_reject_empty_outputs() -> None:
    checks = [
        (gen.generate_docx, {"filename": "empty", "content": []}),
        (gen.generate_xlsx, {"filename": "empty", "sheets": []}),
        (gen.generate_pptx, {"filename": "empty", "slides": []}),
        (gen.generate_pdf, {"filename": "empty", "content": []}),
    ]
    for func, payload in checks:
        try:
            func(payload)
        except ValueError:
            continue
        raise AssertionError(f"{func.__name__} accepted empty payload")


def main() -> None:
    tests = [
        test_docx_generation_accepts_content_ir_blocks,
        test_xlsx_generation_accepts_content_ir_tables,
        test_pptx_generation_accepts_content_ir_elements,
        test_pdf_generation_accepts_content_ir_blocks,
        test_generators_reject_empty_outputs,
    ]
    print("=" * 60)
    print("office-gen sandbox test")
    print("=" * 60)
    for test in tests:
        test()
        print(f"  [PASS] {test.__name__}")
    print("=" * 60)
    print("PASS: office-gen sandbox test")


if __name__ == "__main__":
    main()
