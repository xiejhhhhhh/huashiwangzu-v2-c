from app.core.exceptions import ValidationError
from app.middleware.auth import require_permission
from app.models.user import User
from app.schemas.common import ApiResponse
from app.services.module_registry import register_capability
from app.services.parser_resource_diagnostics import store_extracted_resources_with_diagnostics
from app.services.uploaded_file_runner import run_uploaded_file_capability
from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from .parser import EmailParseError, parse_email_file

router = APIRouter(prefix="/api/email-parser", tags=["email-parser"])


class ParseRequest(BaseModel):
    file_id: int = Field(gt=0)


def _require_positive_file_id(params: dict) -> int:
    try:
        file_id = int(params.get("file_id", 0))
    except (TypeError, ValueError) as exc:
        raise ValidationError("file_id must be a positive integer") from exc
    if file_id <= 0:
        raise ValidationError("file_id must be a positive integer")
    return file_id


async def _parse(params: dict, caller: str) -> dict:
    allowed = {"eml", "msg"}
    file_id = _require_positive_file_id(params)

    def parse_file(file_id, _file, full_path, ext):
        try:
            return parse_email_file(file_id, full_path, ext)
        except EmailParseError as exc:
            raise ValidationError(str(exc)) from exc

    try:
        result = await run_uploaded_file_capability({"file_id": file_id}, caller, allowed, parse_file)
    except ValueError as exc:
        raise ValidationError(str(exc)) from exc
    return await store_extracted_resources_with_diagnostics(result, caller=caller, parser="email-parser")


@router.get("/health")
async def health():
    return ApiResponse(data={"module": "email-parser", "status": "ok"})


@router.post("/parse")
async def call_parse(payload: ParseRequest, user: User = Depends(require_permission("viewer"))):
    result = await _parse({"file_id": payload.file_id}, f"user:{user.id}")
    return ApiResponse(data=result)


register_capability(
    "email-parser", "parse", _parse,
    description="Parse EML/MSG email files into unified content blocks with headers and body",
    brief="解析邮件文件",
    parameters={"file_id": {"type": "int", "description": "File ID in file storage"}},
    min_role="viewer",
)
