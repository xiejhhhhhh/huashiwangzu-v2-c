import asyncio
import re
import shutil
import tempfile
import zipfile
from pathlib import Path
from xml.etree import ElementTree as ET

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
            try:
                converted_path = await convert_file(full_path, "docx", tmpdir)
                result = await asyncio.to_thread(parse_docx_file, file_id, Path(converted_path))
                result["metadata"]["repaired_from"] = "docx"
                result["warnings"].append("repaired_from_docx")
                result["warnings"].append(str(first_error))
                return result
            except (RuntimeError, FileNotFoundError, TimeoutError, DocxParseError) as repair_error:
                return await _parse_docx_text_fallback(file_id, full_path, first_error, repair_error, tmpdir)
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


async def _parse_docx_text_fallback(
    file_id: int,
    full_path: Path,
    first_error: BaseException,
    repair_error: BaseException,
    tmpdir: str,
) -> dict:
    try:
        text_path = await convert_doc_to_text_with_textutil(full_path, tmpdir, timeout_seconds=30)
        return await asyncio.to_thread(
            _parse_text_fallback_result,
            file_id,
            full_path,
            Path(text_path).read_text(encoding="utf-8", errors="replace"),
            "textutil_docx_text_extraction",
            [first_error, repair_error],
            "docx",
        )
    except (RuntimeError, FileNotFoundError, TimeoutError) as text_error:
        try:
            text = await asyncio.to_thread(_extract_docx_zip_text, full_path)
        except (OSError, RuntimeError, zipfile.BadZipFile, ET.ParseError) as zip_error:
            raise RuntimeError(
                f"{_parser_error_message(repair_error)}; "
                f"textutil fallback unavailable: {_parser_error_message(text_error)}; "
                f"zip text fallback unavailable: {_parser_error_message(zip_error)}"
            ) from zip_error
        return await asyncio.to_thread(
            _parse_text_fallback_result,
            file_id,
            full_path,
            text,
            "docx_zip_text_extraction",
            [first_error, repair_error, text_error],
            "docx",
        )


def _parse_doc_text_fallback(
    file_id: int,
    full_path: Path,
    text_path: Path,
    fallback_reason: BaseException | str,
) -> dict:
    text = text_path.read_text(encoding="utf-8", errors="replace")
    return _parse_text_fallback_result(
        file_id,
        full_path,
        text,
        "textutil_doc_text_extraction",
        [fallback_reason],
        "doc",
    )


def _parse_text_fallback_result(
    file_id: int,
    full_path: Path,
    text: str,
    fallback_parser: str,
    fallback_reasons: list[BaseException | str],
    source_format: str,
) -> dict:
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
                "fallback": fallback_parser,
            },
        }
        for index, paragraph in enumerate(paragraphs, start=1)
    ]
    convert_message = "; ".join(
        message
        for message in (_fallback_reason_message(reason) for reason in fallback_reasons)
        if message
    )
    mime_type = (
        "application/msword"
        if source_format == "doc"
        else "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    )
    return {
        "schema_version": "content-ir/v1",
        "content_type": "document",
        "title": full_path.name,
        "file_id": file_id,
        "format": source_format,
        "source_file_id": file_id,
        "source_module": "docx-parser",
        "parser": "docx-parser",
        "source": {
            "module": "docx-parser",
            "file_id": file_id,
            "filename": full_path.name,
            "mime_type": mime_type,
        },
        "blocks": blocks,
        "resources": [],
        "metadata": {
            "parser": "docx-parser",
            "format": source_format,
            "filename": full_path.name,
            "paragraph_count": len(blocks),
            "resource_count": 0,
            "converted_from": source_format,
            "fallback_parser": fallback_parser,
            "fallback_reason": convert_message,
        },
        "warnings": [f"converted_from_{source_format}_text_fallback", convert_message],
        "resource_diagnostics": [],
    }


def _fallback_reason_message(reason: BaseException | str) -> str:
    if isinstance(reason, BaseException):
        return _parser_error_message(reason)
    return str(reason).strip()


def _extract_docx_zip_text(full_path: Path) -> str:
    with zipfile.ZipFile(full_path) as archive:
        try:
            document_xml = archive.read("word/document.xml")
        except KeyError as exc:
            raise RuntimeError("DOCX archive does not contain word/document.xml") from exc
    root = ET.fromstring(document_xml)
    paragraphs: list[str] = []
    for paragraph in root.iter():
        if not paragraph.tag.endswith("}p"):
            continue
        parts: list[str] = []
        for node in paragraph.iter():
            if node.tag.endswith("}t") and node.text:
                parts.append(node.text)
            elif node.tag.endswith("}tab"):
                parts.append("\t")
            elif node.tag.endswith("}br"):
                parts.append("\n")
        paragraph_text = re.sub(r"[ \t]+", " ", "".join(parts)).strip()
        if paragraph_text:
            paragraphs.append(paragraph_text)
    text = "\n\n".join(paragraphs).strip()
    if not text:
        raise RuntimeError("DOCX zip text fallback extracted no text")
    return text


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
