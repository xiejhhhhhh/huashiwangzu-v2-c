from __future__ import annotations

import base64
from pathlib import Path
from typing import Any

from app.services.parser_resource_diagnostics import build_resource_diagnostic
from docx import Document as DocxDocument
from docx.oxml.ns import qn
from docx.oxml.table import CT_Tbl
from docx.oxml.text.paragraph import CT_P
from docx.table import Table
from docx.text.paragraph import Paragraph


class DocxParseError(ValueError):
    """Raised when the input is not a parseable DOCX document."""


def parse_docx_file(file_id: int, full_path: Path) -> dict[str, Any]:
    try:
        doc = DocxDocument(str(full_path))
    except Exception as exc:
        raise DocxParseError(f"Failed to parse DOCX file: {exc}") from exc

    blocks: list[dict[str, Any]] = []
    resources: list[dict[str, Any]] = []
    resource_diagnostics: list[dict[str, Any]] = []
    resource_counter = 0

    for child in doc.element.body.iterchildren():
        if isinstance(child, CT_P):
            para = Paragraph(child, doc)
            text = "\n".join(line.rstrip() for line in para.text.splitlines()).strip()
            if text:
                style_name = str(para.style.name) if para.style else ""
                block_type = "heading" if ("heading" in style_name.lower() or "标题" in style_name) else "paragraph"
                blocks.append({"type": block_type, "text": text, "page": None, "resource_ref": None})

            for rel_id in _iter_paragraph_image_rel_ids(para):
                resource_counter += 1
                resource = _extract_image_resource(doc, rel_id, resource_counter, resource_diagnostics)
                blocks.append({"type": "image", "text": "", "page": None, "resource_ref": resource_counter})
                resources.append(resource)

        elif isinstance(child, CT_Tbl):
            table = Table(child, doc)
            table_text = _table_to_text(table)
            if table_text:
                blocks.append({"type": "table", "text": table_text, "page": None, "resource_ref": None})

    return {
        "file_id": file_id,
        "format": "docx",
        "blocks": blocks,
        "resources": resources,
        "resource_diagnostics": resource_diagnostics,
    }


def _table_to_text(table: Table) -> str:
    rows = []
    for row in table.rows:
        cells = [cell.text.strip() for cell in row.cells]
        if any(cells):
            rows.append(" | ".join(cells))
    return "\n".join(rows).strip()


def _iter_paragraph_image_rel_ids(para: Paragraph) -> list[str]:
    rel_ids: list[str] = []
    for node in para._p.iter():
        if not str(node.tag).endswith("}blip"):
            continue
        rel_id = node.get(qn("r:embed")) or node.get(qn("r:link"))
        if rel_id:
            rel_ids.append(rel_id)
    return rel_ids


def _extract_image_resource(
    doc: DocxDocument,
    rel_id: str,
    resource_id: int,
    resource_diagnostics: list[dict[str, Any]],
) -> dict[str, Any]:
    img_bytes = b""
    mime_type = "image/png"
    target_ref = ""
    extract_diagnostic_recorded = False

    try:
        rel = doc.part.rels[rel_id]
        target_ref = str(getattr(rel, "target_ref", "") or "")
        target_part = rel.target_part
        img_bytes = target_part.blob
        mime_type = getattr(target_part, "content_type", None) or "image/png"
    except Exception as exc:
        extract_diagnostic_recorded = True
        resource_diagnostics.append(build_resource_diagnostic(
            parser="docx-parser",
            stage="extract",
            status="degraded",
            code="resource_extract_failed",
            message="Failed to extract DOCX embedded image bytes.",
            resource={
                "id": resource_id,
                "type": "image",
                "filename": _image_filename(target_ref),
                "mime_type": mime_type,
                "description": f"DOCX embedded image ({target_ref or rel_id})",
            },
            error=exc,
        ))

    return {
        "id": resource_id,
        "type": "image",
        "mime_type": mime_type,
        "filename": _image_filename(target_ref),
        "description": f"DOCX embedded image ({target_ref or rel_id})",
        "_resource_diagnostic_recorded": extract_diagnostic_recorded,
        "_bytes_b64": base64.b64encode(img_bytes).decode("ascii") if img_bytes else "",
    }


def _image_filename(target_ref: str) -> str:
    if "/" in target_ref:
        return target_ref.rsplit("/", 1)[-1] or "image.png"
    return target_ref or "image.png"
