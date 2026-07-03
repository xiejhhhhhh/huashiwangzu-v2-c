from pathlib import Path

from app.core.exceptions import AppException, ValidationError
from app.middleware.auth import require_permission
from app.models.user import User
from app.schemas.common import ApiResponse
from app.services.module_registry import register_capability
from app.services.uploaded_file_runner import run_uploaded_file_capability
from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from .parser import (
    SUPPORTED_EXTS,
    StructuredFileTooLargeError,
    StructuredParseError,
    parse_structured_file,
)

router = APIRouter(prefix="/api/structured-parser", tags=["structured-parser"])


class ParseRequest(BaseModel):
    file_id: int = Field(gt=0)


async def _parse(params: dict, caller: str) -> dict:
    def parse_file(file_id: int, _file: object, full_path: Path, ext: str) -> dict[str, object]:
        try:
            return parse_structured_file(file_id, full_path, ext)
        except StructuredFileTooLargeError as exc:
            raise AppException(str(exc), code="FILE_TOO_LARGE", status_code=413) from exc
        except StructuredParseError as exc:
            raise ValidationError(str(exc)) from exc

    try:
        return await run_uploaded_file_capability(params, caller, SUPPORTED_EXTS, parse_file)
    except (TypeError, ValueError) as exc:
        raise ValidationError("file_id must be a positive integer") from exc


@router.get("/health")
async def health():
    return ApiResponse(data={"module": "structured-parser", "status": "ok"})


@router.post("/parse")
async def call_parse(payload: ParseRequest, user: User = Depends(require_permission("viewer"))):
    result = await _parse({"file_id": payload.file_id}, f"user:{user.id}")
    return ApiResponse(data=result)


register_capability(
    "structured-parser", "parse", _parse,
    description="Parse JSON/YAML files into unified content blocks",
    brief="解析 JSON/YAML 结构化文件",
    parameters={"file_id": {"type": "int", "description": "File ID in file storage"}},
    min_role="viewer",
)
