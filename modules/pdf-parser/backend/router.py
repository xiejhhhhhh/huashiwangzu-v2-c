from app.core.exceptions import ValidationError
from app.middleware.auth import require_permission
from app.models.user import User
from app.schemas.common import ApiResponse
from app.services.module_registry import register_capability
from app.services.parser_resource_diagnostics import (
    build_resource_diagnostic,
    store_extracted_resources_with_diagnostics,
)
from app.services.uploaded_file_runner import run_uploaded_file_capability
from fastapi import APIRouter, Depends
from pydantic import BaseModel

router = APIRouter(prefix="/api/pdf-parser", tags=["pdf-parser"])


class ParseRequest(BaseModel):
    file_id: int


def _require_positive_file_id(params: dict) -> int:
    try:
        file_id = int(params.get("file_id", 0))
    except (TypeError, ValueError) as exc:
        raise ValidationError("file_id must be a positive integer") from exc
    if file_id <= 0:
        raise ValidationError("file_id must be a positive integer")
    return file_id


def _ensure_non_empty_parse_result(result: dict) -> None:
    blocks = result.get("blocks")
    resources = result.get("resources")
    if not isinstance(blocks, list) or not isinstance(resources, list):
        raise ValidationError("PDF parser returned an invalid result shape")
    if not blocks and not resources:
        raise ValidationError("PDF parsing produced no content blocks or embedded resources")


async def _parse(params: dict, caller: str) -> dict:
    """Parse PDF file into unified content blocks. Called via cross-module capability."""
    import base64

    import pdfplumber

    allowed = {"pdf"}
    file_id = _require_positive_file_id(params)

    def parse_file(file_id, _file, full_path, _ext):
        blocks = []
        resources = []
        resource_diagnostics = []
        resource_counter = 0

        with pdfplumber.open(str(full_path)) as pdf:
            for page_idx, page in enumerate(pdf.pages):
                pno = page_idx + 1

                text = page.extract_text() or ""
                lines = [line.rstrip() for line in text.splitlines() if line.strip()]
                if lines:
                    block_text = "\n".join(lines).strip()
                    if block_text:
                        block_type = "heading" if pno == 1 and len(lines) <= 5 else "paragraph"
                        blocks.append({"type": block_type, "text": block_text, "page": pno, "resource_ref": None})

                tables = page.extract_tables() or []
                for table in tables:
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

                    img_bytes = b""
                    extract_diagnostic_recorded = False
                    try:
                        import fitz
                        pdf_doc = fitz.open(str(full_path))
                        try:
                            pix = pdf_doc[page_idx].get_pixmap()
                            img_bytes = pix.tobytes("png")
                        finally:
                            pdf_doc.close()
                    except ImportError as exc:
                        extract_diagnostic_recorded = True
                        resource_diagnostics.append(build_resource_diagnostic(
                            parser="pdf-parser",
                            stage="extract",
                            status="degraded",
                            code="resource_extract_dependency_missing",
                            message="PyMuPDF is unavailable; PDF embedded image bytes were not rendered.",
                            resource={
                                "id": resource_counter,
                                "type": "image",
                                "page": pno,
                                "mime_type": "image/png",
                                "filename": f"page{pno}_xref{xref}.png",
                                "description": f"PDF page {pno} embedded image (xref={xref})",
                            },
                            error=exc,
                        ))
                    except Exception as exc:
                        extract_diagnostic_recorded = True
                        resource_diagnostics.append(build_resource_diagnostic(
                            parser="pdf-parser",
                            stage="extract",
                            status="degraded",
                            code="resource_extract_failed",
                            message="Failed to render PDF embedded image bytes.",
                            resource={
                                "id": resource_counter,
                                "type": "image",
                                "page": pno,
                                "mime_type": "image/png",
                                "filename": f"page{pno}_xref{xref}.png",
                                "description": f"PDF page {pno} embedded image (xref={xref})",
                            },
                            error=exc,
                        ))

                    resources.append({
                        "id": resource_counter,
                        "type": "image",
                        "page": pno,
                        "mime_type": "image/png",
                        "filename": f"page{pno}_xref{xref}.png",
                        "description": f"PDF page {pno} embedded image (xref={xref})",
                        "_resource_diagnostic_recorded": extract_diagnostic_recorded,
                        "_bytes_b64": base64.b64encode(img_bytes).decode("ascii") if img_bytes else "",
                    })

        return {
            "file_id": file_id,
            "format": "pdf",
            "blocks": blocks,
            "resources": resources,
            "resource_diagnostics": resource_diagnostics,
        }

    result = await run_uploaded_file_capability({"file_id": file_id}, caller, allowed, parse_file)
    _ensure_non_empty_parse_result(result)
    return await store_extracted_resources_with_diagnostics(result, caller=caller, parser="pdf-parser")


@router.get("/health")
async def health():
    return ApiResponse(data={"module": "pdf-parser", "status": "ok"})


@router.post("/parse")
async def call_parse(payload: ParseRequest, user: User = Depends(require_permission("viewer"))):
    result = await _parse({"file_id": payload.file_id}, f"user:{user.id}")
    return ApiResponse(data=result)


# Register capability at import time
register_capability(
    "pdf-parser", "parse", _parse,
    description="Parse PDF files into unified content blocks",
    brief="解析 PDF 文档",
    parameters={"file_id": {"type": "int", "description": "File ID in file storage"}},
    min_role="viewer",
)
