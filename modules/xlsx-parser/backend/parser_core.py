"""Pure XLSX/CSV parsing logic for xlsx-parser."""
from __future__ import annotations

import csv
import io
from collections.abc import Iterable
from datetime import date, datetime, time
from itertools import zip_longest
from pathlib import Path
from zipfile import BadZipFile

from openpyxl import load_workbook
from openpyxl.utils.exceptions import InvalidFileException

MAX_ROWS_PER_SHEET = 5000
SUPPORTED_EXTS = {"xlsx", "csv"}


class SpreadsheetParseError(ValueError):
    """Raised when the input is not a parseable supported spreadsheet."""


def _decode_text_bytes(raw: bytes) -> str:
    for encoding in ("utf-8", "utf-8-sig", "gbk", "gb2312", "latin-1"):
        try:
            return raw.decode(encoding)
        except UnicodeDecodeError:
            continue
    return raw.decode("utf-8", errors="replace")


def _format_cell(value: object, formula_value: object = None) -> str:
    if value is None:
        if isinstance(formula_value, str) and formula_value.startswith("="):
            return formula_value.strip()
        return ""
    if isinstance(value, datetime):
        return value.isoformat(sep=" ")
    if isinstance(value, date | time):
        return value.isoformat()
    return str(value).strip()


def _row_to_text(values: Iterable[object], formulas: Iterable[object] = ()) -> str:
    cells = [
        _format_cell(value, formula)
        for value, formula in zip_longest(values, formulas, fillvalue=None)
    ]
    return " | ".join(cells).rstrip()


def _empty_result(file_id: int, ext: str, warnings: list[str], metadata: dict) -> dict:
    return {
        "file_id": file_id,
        "format": ext,
        "blocks": [],
        "resources": [],
        "warnings": warnings,
        "metadata": metadata,
    }


def parse_csv_file(file_id: int, path: Path, ext: str = "csv") -> dict:
    raw = path.read_bytes()
    content = _decode_text_bytes(raw)
    reader = csv.reader(io.StringIO(content))
    rows: list[str] = []
    warnings: list[str] = []
    truncated = False

    for row_index, row in enumerate(reader, start=1):
        row_text = " | ".join(cell.strip() for cell in row).rstrip()
        if row_text.strip():
            rows.append(row_text)
        if len(rows) >= MAX_ROWS_PER_SHEET:
            truncated = True
            rows.append(f"[... truncated at {MAX_ROWS_PER_SHEET} rows]")
            break

    metadata = {
        "row_limit": MAX_ROWS_PER_SHEET,
        "rows_emitted": min(len(rows), MAX_ROWS_PER_SHEET),
        "truncated": truncated,
    }
    if not rows:
        warnings.append("empty_csv")
        return _empty_result(file_id, ext, warnings, metadata)
    if truncated:
        warnings.append("row_limit_reached")

    return {
        "file_id": file_id,
        "format": ext,
        "blocks": [{"type": "table", "text": "\n".join(rows), "page": None, "resource_ref": None}],
        "resources": [],
        "warnings": warnings,
        "metadata": metadata,
    }


def parse_xlsx_file(file_id: int, path: Path) -> dict:
    warnings: list[str] = []
    blocks: list[dict] = []
    sheet_metadata: list[dict] = []
    value_workbook = None
    formula_workbook = None

    try:
        value_workbook = load_workbook(path, read_only=True, data_only=True)
        formula_workbook = load_workbook(path, read_only=True, data_only=False)
        for sheet_index, sheet_name in enumerate(value_workbook.sheetnames, start=1):
            value_sheet = value_workbook[sheet_name]
            formula_sheet = formula_workbook[sheet_name]
            rows: list[str] = []
            truncated = False

            paired_rows = zip_longest(
                value_sheet.iter_rows(values_only=True),
                formula_sheet.iter_rows(values_only=True),
                fillvalue=(),
            )
            for value_row, formula_row in paired_rows:
                row_text = _row_to_text(value_row or (), formula_row or ())
                if row_text.strip():
                    rows.append(row_text)
                if len(rows) >= MAX_ROWS_PER_SHEET:
                    truncated = True
                    rows.append(f"[... truncated at {MAX_ROWS_PER_SHEET} rows]")
                    break

            sheet_metadata.append({
                "name": sheet_name,
                "page": sheet_index,
                "rows_emitted": min(len(rows), MAX_ROWS_PER_SHEET),
                "truncated": truncated,
            })
            if truncated:
                warnings.append(f"row_limit_reached:{sheet_name}")
            if rows:
                block_text = f"[Sheet: {sheet_name}]\n" + "\n".join(rows)
                blocks.append({
                    "type": "table",
                    "text": block_text,
                    "page": sheet_index,
                    "resource_ref": None,
                })
            else:
                warnings.append(f"empty_sheet:{sheet_name}")
    except (BadZipFile, InvalidFileException, OSError, KeyError, ValueError) as exc:
        raise SpreadsheetParseError(f"Failed to parse XLSX file: {exc}") from exc
    finally:
        if value_workbook is not None:
            value_workbook.close()
        if formula_workbook is not None:
            formula_workbook.close()

    if not blocks:
        warnings.append("empty_workbook")

    return {
        "file_id": file_id,
        "format": "xlsx",
        "blocks": blocks,
        "resources": [],
        "warnings": warnings,
        "metadata": {
            "sheet_count": len(sheet_metadata),
            "sheets": sheet_metadata,
            "row_limit": MAX_ROWS_PER_SHEET,
        },
    }


def parse_spreadsheet_file(file_id: int, path: Path, ext: str) -> dict:
    normalized_ext = ext.lower().lstrip(".")
    if normalized_ext == "xlsx":
        return parse_xlsx_file(file_id, path)
    if normalized_ext == "csv":
        return parse_csv_file(file_id, path, normalized_ext)
    raise SpreadsheetParseError(
        f"Unsupported format '{normalized_ext}'. Allowed: {', '.join(sorted(SUPPORTED_EXTS))}"
    )
