from app.core.exceptions import ValidationError
from app.middleware.auth import require_permission
from app.models.user import User
from app.schemas.common import ApiResponse
from app.services.module_registry import register_capability
from app.services.uploaded_file_runner import run_uploaded_file_capability
from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from .parser import SUPPORTED_EXTS, TextParseError, parse_text_file

router = APIRouter(prefix="/api/text-parser", tags=["text-parser"])


class ParseRequest(BaseModel):
    file_id: int = Field(gt=0)


async def _parse(params: dict, caller: str) -> dict:
    def parse_file(file_id, _file, full_path, ext):
        try:
            return parse_text_file(file_id, full_path, ext)
        except TextParseError as exc:
            raise ValidationError(str(exc)) from exc

    try:
        return await run_uploaded_file_capability(params, caller, SUPPORTED_EXTS, parse_file)
    except ValueError as exc:
        raise ValidationError(str(exc)) from exc


@router.get("/health")
async def health():
    return ApiResponse(data={"module": "text-parser", "status": "ok"})


@router.post("/parse")
async def call_parse(payload: ParseRequest, user: User = Depends(require_permission("viewer"))):
    result = await _parse({"file_id": payload.file_id}, f"user:{user.id}")
    return ApiResponse(data=result)


register_capability(
    "text-parser", "parse", _parse,
    description="Parse TXT/MD files into unified content blocks",
    brief="解析文本文件",
    parameters={"file_id": {"type": "int", "description": "File ID in file storage"}},
    min_role="viewer",
)
