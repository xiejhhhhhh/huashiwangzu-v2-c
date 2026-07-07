import asyncio
import shutil
import tempfile
from pathlib import Path

from app.core.exceptions import ValidationError
from app.middleware.auth import require_permission
from app.models.user import User
from app.schemas.common import ApiResponse
from app.services.module_registry import register_capability
from app.services.office_conversion import convert_doc_to_text_with_textutil, convert_file
from app.services.parser_resource_diagnostics import store_extracted_resources_with_diagnostics
from app.services.uploaded_file_runner import run_uploaded_file_capability
from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from .parser import DocxParseError, parse_docx_file

router = APIRouter(prefix="/api/docx-parser", tags=["docx-parser"])
PARSER_NAME = "docx-parser"


class ParseRequest(BaseModel):
    file_id: int = Field(gt=0)


async def _parse_docx_with_repair(file_id: int, full_path: Path) -> dict:
    try:
        return await asyncio.to_thread(parse_docx_file, file_id, full_path)
    except DocxParseError as first_error:
        tmpdir = tempfile.mkdtemp(prefix="docx_repair_")
        try:
            converted_path = await convert_file(full_path, "docx", tmpdir)
            result = await asyncio.to_thread(parse_docx_file, file_id, Path(converted_path))
            result["metadata"]["repaired_from"] = "docx"
            result["warnings"].append("repaired_from_docx")
            result["warnings"].append(str(first_error))
            return result
        finally:
            await asyncio.to_thread(shutil.rmtree, tmpdir, True)


async def _parse(params: dict, caller: str) -> dict:
    allowed = {"doc", "docx"}

    async def parse_file(file_id, _file, full_path, ext):
        try:
            if ext == "doc":
                tmpdir = tempfile.mkdtemp(prefix="doc_parser_")
                try:
                    try:
                        text_path = await convert_doc_to_text_with_textutil(full_path, tmpdir, timeout_seconds=30)
                        return await asyncio.to_thread(
                            _parse_doc_text_fallback,
                            file_id,
                            full_path,
                            Path(text_path),
                            "textutil_doc_text_extraction",
                        )
                    except (RuntimeError, FileNotFoundError, TimeoutError) as text_exc:
                        text_fallback_error = text_exc
                    try:
                        converted_path = await convert_file(full_path, "docx", tmpdir)
                        result = await asyncio.to_thread(parse_docx_file, file_id, Path(converted_path))
                    except (RuntimeError, FileNotFoundError, TimeoutError) as convert_exc:
                        raise RuntimeError(
                            f"{_parser_error_message(convert_exc)}; "
                            f"textutil fallback unavailable: {_parser_error_message(text_fallback_error)}"
                        ) from convert_exc
                    result["format"] = "doc"
                    result["metadata"]["format"] = "doc"
                    result["metadata"]["converted_from"] = "doc"
                    result["warnings"].append("converted_from_doc")
                    return result
                finally:
                    await asyncio.to_thread(shutil.rmtree, tmpdir, True)
            return await _parse_docx_with_repair(file_id, full_path)
        except (DocxParseError, RuntimeError, ValueError, FileNotFoundError, TimeoutError) as exc:
            raise ValidationError(_parser_error_message(exc)) from exc

    try:
        result = await run_uploaded_file_capability(params, caller, allowed, parse_file)
    except ValueError as exc:
        raise ValidationError(_parser_error_message(exc)) from exc
    return await store_extracted_resources_with_diagnostics(result, caller=caller, parser="docx-parser")


def _parser_error_message(exc: BaseException) -> str:
    message = str(exc).strip()
    if message:
        return message
    return f"{PARSER_NAME} failed without diagnostic output ({type(exc).__name__})"


def _parse_doc_text_fallback(
    file_id: int,
    full_path: Path,
    text_path: Path,
    fallback_reason: BaseException | str,
) -> dict:
    text = text_path.read_text(encoding="utf-8", errors="replace")
    paragraphs = [part.strip() for part in text.split("\n\n") if part.strip()]
    if not paragraphs and text.strip():
        paragraphs = [line.strip() for line in text.splitlines() if line.strip()]
    blocks = [
        {
            "type": "paragraph",
            "text": paragraph,
            "page": None,
            "resource_ref": None,
            "source_ref": {
                "module": "docx-parser",
                "file_id": file_id,
                "paragraph": index,
                "fallback": "textutil",
            },
        }
        for index, paragraph in enumerate(paragraphs, start=1)
    ]
    convert_message = (
        _parser_error_message(fallback_reason)
        if isinstance(fallback_reason, BaseException)
        else str(fallback_reason).strip()
    )
    return {
        "schema_version": "content-ir/v1",
        "content_type": "document",
        "title": full_path.name,
        "file_id": file_id,
        "format": "doc",
        "source_file_id": file_id,
        "source_module": "docx-parser",
        "parser": "docx-parser",
        "source": {
            "module": "docx-parser",
            "file_id": file_id,
            "filename": full_path.name,
            "mime_type": "application/msword",
        },
        "blocks": blocks,
        "resources": [],
        "metadata": {
            "parser": "docx-parser",
            "format": "doc",
            "filename": full_path.name,
            "paragraph_count": len(blocks),
            "resource_count": 0,
            "converted_from": "doc",
            "fallback_parser": "textutil",
            "fallback_reason": convert_message,
        },
        "warnings": ["converted_from_doc_text_fallback", convert_message],
        "resource_diagnostics": [],
    }


@router.get("/health")
async def health():
    return ApiResponse(data={"module": "docx-parser", "status": "ok"})


@router.post("/parse")
async def call_parse(payload: ParseRequest, user: User = Depends(require_permission("viewer"))):
    result = await _parse({"file_id": payload.file_id}, f"user:{user.id}")
    return ApiResponse(data=result)


register_capability(
    "docx-parser", "parse", _parse,
    description="Parse DOC/DOCX files into unified content blocks",
    brief="解析 DOC/DOCX 文档",
    parameters={"file_id": {"type": "int", "description": "File ID in file storage"}},
    min_role="viewer",
)
