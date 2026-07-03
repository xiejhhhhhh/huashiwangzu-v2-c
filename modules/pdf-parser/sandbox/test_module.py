"""Sandbox test for pdf-parser module.

Validates that a real PDF sample produces non-empty unified content blocks.
Usage: ../../../backend/.venv/bin/python test_module.py  (from modules/pdf-parser/sandbox/)
"""
from pathlib import Path
from typing import Any

SAMPLE = Path(__file__).resolve().parent / "samples" / "sample.pdf"

import pdfplumber


def parse_pdf(path: Path) -> dict[str, Any]:
    blocks = []
    resources = []
    resource_counter = 0
    with pdfplumber.open(str(path)) as pdf:
        for page_idx, page in enumerate(pdf.pages):
            pno = page_idx + 1
            text = page.extract_text() or ""
            lines = [line.rstrip() for line in text.splitlines() if line.strip()]
            if lines:
                block_text = "\n".join(lines).strip()
                if block_text:
                    block_type = "heading" if pno == 1 and len(lines) <= 5 else "paragraph"
                    blocks.append({"type": block_type, "text": block_text, "page": pno, "resource_ref": None})
            for table in (page.extract_tables() or []):
                if not table:
                    continue
                rows = []
                for row in table:
                    cells = [str(c).strip() if c else "" for c in row]
                    rows.append(" | ".join(cells))
                table_text = "\n".join(rows)
                if table_text.strip():
                    blocks.append({"type": "table", "text": table_text, "page": pno, "resource_ref": None})
            for img in page.images:
                resource_counter += 1
                xref = img.get("xref") or img.get("name", "")
                blocks.append({"type": "image", "text": "", "page": pno, "resource_ref": resource_counter})
                resources.append({
                    "id": resource_counter,
                    "type": "image",
                    "page": pno,
                    "mime_type": "image/png",
                    "filename": f"page{pno}_xref{xref}.png",
                    "description": f"PDF page {pno} embedded image (xref={xref})",
                })
    return {"file_id": 0, "format": "pdf", "blocks": blocks, "resources": resources}


def validate(result: dict[str, Any]) -> None:
    assert isinstance(result, dict) and all(k in result for k in ("file_id", "format", "blocks", "resources"))
    assert result["format"] == "pdf"
    blocks = result["blocks"]
    resources = result["resources"]
    assert isinstance(blocks, list)
    assert isinstance(resources, list)
    assert blocks or resources, "Expected the sample PDF to produce content blocks or resources"
    assert any(block.get("text", "").strip() for block in blocks), "Expected sample PDF text extraction to be non-empty"
    for block in blocks:
        assert isinstance(block, dict)
        assert all(key in block for key in ("type", "text", "page", "resource_ref"))
        assert block["type"] in ("heading", "paragraph", "table", "image")
        assert isinstance(block["page"], int) and block["page"] >= 1
    for resource in resources:
        assert isinstance(resource, dict)
        assert all(key in resource for key in ("id", "type", "page", "mime_type", "filename", "description"))
        assert isinstance(resource["page"], int) and resource["page"] >= 1
    print("  Validation PASS (%d blocks, %d resources)" % (len(result["blocks"]), len(result["resources"])))


def test_sample_pdf_parses_real_content() -> None:
    assert SAMPLE.exists(), f"Sample not found: {SAMPLE}"
    result = parse_pdf(SAMPLE)
    validate(result)


def test_empty_parse_result_is_rejected() -> None:
    empty = {"file_id": 0, "format": "pdf", "blocks": [], "resources": []}
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
    result = parse_pdf(SAMPLE)
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
