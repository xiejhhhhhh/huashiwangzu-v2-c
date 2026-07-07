import asyncio
import importlib.util
import shutil
import tempfile
from pathlib import Path

from app.core.exceptions import ValidationError
from app.middleware.auth import require_permission
from app.models.user import User
from app.schemas.common import ApiResponse
from app.services.module_registry import register_capability
from app.services.office_conversion import convert_file
from app.services.uploaded_file_runner import run_uploaded_file_capability
from fastapi import APIRouter, Depends
from pydantic import BaseModel

_PARSER_CORE_PATH = Path(__file__).with_name("parser_core.py")
_PARSER_CORE_SPEC = importlib.util.spec_from_file_location("xlsx_parser_core", _PARSER_CORE_PATH)
if _PARSER_CORE_SPEC is None or _PARSER_CORE_SPEC.loader is None:
    raise RuntimeError("Failed to load xlsx parser core")
_parser_core = importlib.util.module_from_spec(_PARSER_CORE_SPEC)
_PARSER_CORE_SPEC.loader.exec_module(_parser_core)

SpreadsheetParseError = _parser_core.SpreadsheetParseError
parse_spreadsheet_file = _parser_core.parse_spreadsheet_file
SUPPORTED_EXTS = _parser_core.SUPPORTED_EXTS

router = APIRouter(prefix="/api/xlsx-parser", tags=["xlsx-parser"])
PARSER_NAME = "xlsx-parser"


class ParseRequest(BaseModel):
    file_id: int


async def _parse(params: dict, caller: str) -> dict:
    async def parse_file(file_id: int, _file: object, full_path: Path, ext: str) -> dict:
        try:
            if ext == "xls":
                tmpdir = tempfile.mkdtemp(prefix="xls_parser_")
                try:
                    converted_path = await convert_file(full_path, "xlsx", tmpdir)
                    result = await asyncio.to_thread(
                        parse_spreadsheet_file,
                        file_id,
                        Path(converted_path),
                        "xlsx",
                    )
                    result["format"] = "xls"
                    result["metadata"]["format"] = "xls"
                    result["metadata"]["converted_from"] = "xls"
                    result["warnings"].append("converted_from_xls")
                    return result
                finally:
                    await asyncio.to_thread(shutil.rmtree, tmpdir, True)
            return await asyncio.to_thread(parse_spreadsheet_file, file_id, full_path, ext)
        except (SpreadsheetParseError, RuntimeError, ValueError, FileNotFoundError, TimeoutError) as exc:
            raise ValidationError(_parser_error_message(exc)) from exc

    try:
        return await run_uploaded_file_capability(params, caller, SUPPORTED_EXTS, parse_file)
    except ValueError as exc:
        raise ValidationError(_parser_error_message(exc)) from exc


def _parser_error_message(exc: BaseException) -> str:
    message = str(exc).strip()
    if message:
        return message
    return f"{PARSER_NAME} failed without diagnostic output ({type(exc).__name__})"


@router.get("/health")
async def health():
    return ApiResponse(data={"module": "xlsx-parser", "status": "ok"})


@router.post("/parse")
async def call_parse(payload: ParseRequest, user: User = Depends(require_permission("viewer"))):
    result = await _parse({"file_id": payload.file_id}, f"user:{user.id}")
    return ApiResponse(data=result)


register_capability(
    "xlsx-parser", "parse", _parse,
    description="Parse XLS/XLSX/CSV files into unified content blocks",
    brief="解析 XLS/XLSX 文档",
    parameters={"file_id": {"type": "int", "description": "File ID in file storage"}},
    min_role="viewer",
)
