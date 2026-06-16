from __future__ import annotations

from app.services.knowledge.extract.types import PageResult

DOCLING_AVAILABLE = False
PDFPLUMBER_AVAILABLE = False
FITZ_AVAILABLE = False

try:
    from docling.document_converter import DocumentConverter
    DOCLING_AVAILABLE = True
except ImportError:
    DocumentConverter = None

try:
    import pdfplumber
    PDFPLUMBER_AVAILABLE = True
except ImportError:
    pdfplumber = None

try:
    import fitz
    FITZ_AVAILABLE = True
except ImportError:
    fitz = None

_DOCLING_CONVERTER = None


def get_docling() -> object:
    global _DOCLING_CONVERTER
    if _DOCLING_CONVERTER is None:
        _DOCLING_CONVERTER = DocumentConverter()
    return _DOCLING_CONVERTER


def extract_docling(file_path: str) -> list[PageResult]:
    converter = get_docling()
    result = converter.convert(file_path)
    pages = []
    for page_num, page in enumerate(result.document.pages.values(), start=1):
        layout_blocks = []
        for item in page.items:
            label = getattr(item, "label", None) or "unknown"
            bbox = getattr(item, "bbox", None)
            text = getattr(item, "text", "") if hasattr(item, "text") else ""
            layout_blocks.append({
                "type": str(label),
                "bbox": str(bbox) if bbox else None,
                "text": text,
            })
        pages.append(PageResult(
            page_num=page_num,
            script_text=page.get_text() or "",
            layout_data={
                "blocks": layout_blocks,
                "page_width": page.size.width,
                "page_height": page.size.height,
            },
        ))
    return pages


def extract_pdfplumber(file_path: str) -> list[PageResult]:
    pages = []
    with pdfplumber.open(file_path) as pdf:
        for page_num, page in enumerate(pdf.pages, start=1):
            script_text = page.extract_text() or ""
            tables = page.extract_tables()
            layout_blocks = []
            if script_text:
                layout_blocks.append({"type": "text", "text": script_text[:200]})
            if tables:
                layout_blocks.append({"type": "tables", "count": len(tables), "data": tables})
            pages.append(PageResult(
                page_num=page_num,
                script_text=script_text,
                layout_data={
                    "blocks": layout_blocks,
                    "total_tables": len(tables) if tables else 0,
                },
            ))
    return pages


def extract_fitz(file_path: str) -> list[PageResult]:
    pages = []
    with fitz.open(file_path) as doc:
        for page_num in range(len(doc)):
            page = doc[page_num]
            blocks = page.get_text("dict").get("blocks", [])
            layout_blocks = [{
                "type": block.get("type", 0),
                "bbox": block.get("bbox"),
                "lines": len(block.get("lines", [])),
            } for block in blocks]
            pages.append(PageResult(
                page_num=page_num + 1,
                script_text=page.get_text() or "",
                layout_data={"blocks": layout_blocks, "total_blocks": len(blocks)},
            ))
    return pages
