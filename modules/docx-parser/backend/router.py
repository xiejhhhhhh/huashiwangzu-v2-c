from app.core.exceptions import ValidationError
from app.middleware.auth import require_permission
from app.models.user import User
from app.schemas.common import ApiResponse
from app.services.module_registry import register_capability
from app.services.parser_resource_diagnostics import store_extracted_resources_with_diagnostics
from app.services.uploaded_file_runner import run_uploaded_file_capability
from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from .parser import DocxParseError, parse_docx_file

router = APIRouter(prefix="/api/docx-parser", tags=["docx-parser"])


class ParseRequest(BaseModel):
    file_id: int = Field(gt=0)


async def _parse(params: dict, caller: str) -> dict:
    allowed = {"docx"}

    def parse_file(file_id, _file, full_path, _ext):
        try:
            return parse_docx_file(file_id, full_path)
        except DocxParseError as exc:
            raise ValidationError(str(exc)) from exc

    try:
        result = await run_uploaded_file_capability(params, caller, allowed, parse_file)
    except ValueError as exc:
        raise ValidationError(str(exc)) from exc
    return await store_extracted_resources_with_diagnostics(result, caller=caller, parser="docx-parser")


@router.get("/health")
async def health():
    return ApiResponse(data={"module": "docx-parser", "status": "ok"})


@router.post("/parse")
async def call_parse(payload: ParseRequest, user: User = Depends(require_permission("viewer"))):
    result = await _parse({"file_id": payload.file_id}, f"user:{user.id}")
    return ApiResponse(data=result)


register_capability(
    "docx-parser", "parse", _parse,
    description="Parse DOCX files into unified content blocks",
    brief="解析 DOCX 文档",
    parameters={"file_id": {"type": "int", "description": "File ID in file storage"}},
    min_role="viewer",
)
