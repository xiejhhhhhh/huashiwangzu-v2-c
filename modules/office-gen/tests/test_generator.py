"""Tests for office-gen: verify generated files are valid and non-empty.

Run from project root:
  cd backend && .venv/bin/python -m pytest ../modules/office-gen/tests/test_generator.py -v
"""
from __future__ import annotations

import importlib.util
import io
import sys
import types
from pathlib import Path

import pytest

# ── Build package hierarchy for "modules/office-gen/backend/" ──
# Since the directory has a hyphen, we use the normalized name "office_gen"

_PROJECT_ROOT = Path(__file__).resolve().parents[3]


def _load_backend_module(name: str) -> types.ModuleType:
    """Load a modules/office-gen/backend/*.py module with proper package prefix."""
    full_name = f"office_gen.{name}"
    file_path = _PROJECT_ROOT / "modules" / "office-gen" / "backend" / f"{name}.py"
    if not file_path.exists():
        raise RuntimeError(f"Module file not found: {file_path}")
    spec = importlib.util.spec_from_file_location(full_name, file_path)
    if not spec or not spec.loader:
        raise RuntimeError(f"Cannot load module: {file_path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[full_name] = module
    spec.loader.exec_module(module)
    return module


# Load the generator module
gen = _load_backend_module("generator")


def _check_docx(data: bytes) -> bool:
    try:
        from docx import Document
        doc = Document(io.BytesIO(data))
        return True
    except Exception:
        return False


def _check_xlsx(data: bytes) -> bool:
    try:
        from openpyxl import load_workbook
        wb = load_workbook(io.BytesIO(data))
        return len(wb.sheetnames) > 0
    except Exception:
        return False


def _check_pptx(data: bytes) -> bool:
    try:
        from pptx import Presentation
        prs = Presentation(io.BytesIO(data))
        return True
    except Exception:
        return False


def _check_pdf(data: bytes) -> bool:
    return data.startswith(b"%PDF") and data.rstrip().endswith(b"%%EOF")


class TestDocxGenerator:
    def test_basic_document(self):
        data = gen.generate_docx({
            "filename": "test",
            "content": [
                {"type": "标题", "text": "Hello World", "level": 1},
                {"type": "段落", "text": "This is a test paragraph", "bold": True},
            ],
        })
        assert len(data) > 100
        assert _check_docx(data)

    def test_with_table(self):
        data = gen.generate_docx({
            "filename": "test_table",
            "content": [
                {"type": "标题", "text": "Table Test", "level": 2},
                {"type": "表格", "header": ["Name", "Age", "City"],
                 "rows": [["Zhang", "28", "Beijing"], ["Li", "32", "Shanghai"]]},
            ],
        })
        assert _check_docx(data)

    def test_empty_content(self):
        data = gen.generate_docx({"filename": "empty", "content": []})
        assert len(data) > 50
        assert _check_docx(data)

    def test_alignment(self):
        data = gen.generate_docx({
            "filename": "align",
            "content": [
                {"type": "段落", "text": "Left", "align": "left"},
                {"type": "段落", "text": "Center", "align": "center"},
            ],
        })
        assert _check_docx(data)


class TestXlsxGenerator:
    def test_basic_spreadsheet(self):
        data = gen.generate_xlsx({
            "filename": "test",
            "sheets": [{
                "name": "Sheet1",
                "columns": ["A", "B", "C"],
                "rows": [[1, 2, 3], [4, 5, 6], [7, 8, 9]],
            }],
        })
        assert len(data) > 100
        assert _check_xlsx(data)

    def test_multiple_sheets(self):
        data = gen.generate_xlsx({
            "filename": "multi",
            "sheets": [
                {"name": "Page1", "columns": ["X"], "rows": [[1]]},
                {"name": "Page2", "columns": ["Y"], "rows": [[2]]},
            ],
        })
        assert _check_xlsx(data)
        wb = __import__("openpyxl").load_workbook(io.BytesIO(data))
        assert wb.sheetnames == ["Page1", "Page2"]

    def test_empty_sheets(self):
        data = gen.generate_xlsx({"filename": "empty", "sheets": []})
        assert _check_xlsx(data)


class TestPptxGenerator:
    def test_basic_presentation(self):
        data = gen.generate_pptx({
            "filename": "test",
            "slides": [
                {"title": "Slide 1", "bullets": ["Point 1", "Point 2"], "notes": "Notes text"},
                {"title": "Slide 2", "bullets": [{"text": "Sub item", "level": 1}]},
            ],
        })
        assert len(data) > 100
        assert _check_pptx(data)

    def test_empty_slides(self):
        data = gen.generate_pptx({"filename": "empty", "slides": []})
        assert _check_pptx(data)


class TestPdfGenerator:
    def test_basic_pdf(self):
        data = gen.generate_pdf({
            "filename": "test",
            "content": [
                {"type": "标题", "text": "Test Document", "level": 1},
                {"type": "段落", "text": "This is a test paragraph."},
            ],
        })
        assert len(data) > 500
        assert _check_pdf(data)

    def test_with_table_pdf(self):
        data = gen.generate_pdf({
            "filename": "test_table",
            "content": [
                {"type": "标题", "text": "Table Test", "level": 2},
                {"type": "表格", "header": ["Name", "Value"],
                 "rows": [["Item A", "100"], ["Item B", "200"]]},
            ],
        })
        assert _check_pdf(data)

    def test_empty_content_pdf(self):
        data = gen.generate_pdf({"filename": "empty", "content": []})
        assert _check_pdf(data)


class TestConverter:
    @staticmethod
    def _get_converter():
        conv = _load_backend_module("converter")
        return conv

    def test_check_libreoffice(self):
        conv = self._get_converter()
        result = conv.check_libreoffice()
        assert result is None or isinstance(result, str)

    def test_get_install_instructions(self):
        conv = self._get_converter()
        instructions = conv.get_install_instructions()
        assert "LibreOffice" in instructions
        assert "brew install" in instructions
