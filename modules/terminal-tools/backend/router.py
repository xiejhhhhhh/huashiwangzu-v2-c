"""FastAPI router for terminal-tools module.

Exposes 8 cross-module capabilities:
  terminal-tools:exec          — Run shell commands in user workspace
  terminal-tools:write_file    — Write files into user workspace
  terminal-tools:read_file     — Read files from user workspace
  terminal-tools:list_workspace— List files in user workspace
  terminal-tools:publish       — Publish workspace files to framework FS
  terminal-tools:import        — Import framework FS files into workspace
  terminal-tools:run_python    — Run Python code in user workspace
  terminal-tools:chart         — Simplified chart generation

All file operations are locked to the user's workspace directory.
Dangerous commands are intercepted.  Execution has timeout + output caps.
"""
import logging
from typing import Any

from app.core.exceptions import ValidationError
from app.middleware.auth import require_permission
from app.models.user import User
from app.schemas.common import ApiResponse
from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from .handlers.exec import _exec
from .handlers.file_ops import _import, _list_workspace, _publish, _read_file, _write_file
from .handlers.python import _chart, _run_python

logger = logging.getLogger("v2.terminal-tools")

router = APIRouter(prefix="/api/terminal-tools", tags=["terminal-tools"])

_DEFAULT_TIMEOUT = 60


def _terminal_response(result: dict[str, Any]) -> ApiResponse[dict[str, Any]]:
    if result.get("success") is False:
        raise ValidationError(str(result.get("error") or "Terminal tool failed"))
    return ApiResponse(data=result)


# ── HTTP request schemas ──

class ExecRequest(BaseModel):
    command: str
    timeout: int = _DEFAULT_TIMEOUT


class WriteFileRequest(BaseModel):
    path: str
    content: str = ""


class ReadFileRequest(BaseModel):
    path: str


class ListWorkspaceRequest(BaseModel):
    path: str = "."


class PublishRequest(BaseModel):
    path: str
    filename: str = ""
    folder_id: int = 0


class ImportFileRequest(BaseModel):
    file_id: int
    target_path: str = ""


class RunPythonRequest(BaseModel):
    code: str
    input_files: list[int] = Field(default_factory=list)
    timeout: int = _DEFAULT_TIMEOUT


class ChartDataPoint(BaseModel):
    x: str | float = ""
    y: float = 0


class ChartRequest(BaseModel):
    data: list[ChartDataPoint]
    chart_type: str = "line"
    title: str = ""
    x_label: str = ""
    y_label: str = ""


# ── HTTP endpoints (direct testing / sandbox debugging) ──

@router.get("/health")
async def health():
    return ApiResponse(data={"module": "terminal-tools", "status": "ok"})


@router.post("/exec")
async def http_exec(
    body: ExecRequest,
    user: User = Depends(require_permission("editor")),
):
    result = await _exec(body.model_dump(), f"user:{user.id}")
    return _terminal_response(result)


@router.post("/write-file")
async def http_write_file(
    body: WriteFileRequest,
    user: User = Depends(require_permission("editor")),
):
    result = await _write_file(body.model_dump(), f"user:{user.id}")
    return _terminal_response(result)


@router.post("/read-file")
async def http_read_file(
    body: ReadFileRequest,
    user: User = Depends(require_permission("viewer")),
):
    result = await _read_file(body.model_dump(), f"user:{user.id}")
    return _terminal_response(result)


@router.post("/list-workspace")
async def http_list_workspace(
    body: ListWorkspaceRequest,
    user: User = Depends(require_permission("viewer")),
):
    result = await _list_workspace(body.model_dump(), f"user:{user.id}")
    return _terminal_response(result)


@router.post("/publish")
async def http_publish(
    body: PublishRequest,
    user: User = Depends(require_permission("editor")),
):
    result = await _publish(body.model_dump(), f"user:{user.id}")
    return _terminal_response(result)


@router.post("/import")
async def http_import(
    body: ImportFileRequest,
    user: User = Depends(require_permission("editor")),
):
    result = await _import(body.model_dump(), f"user:{user.id}")
    return _terminal_response(result)


@router.post("/run-python")
async def http_run_python(
    body: RunPythonRequest,
    user: User = Depends(require_permission("editor")),
):
    result = await _run_python(body.model_dump(), f"user:{user.id}")
    return _terminal_response(result)


@router.post("/chart")
async def http_chart(
    body: ChartRequest,
    user: User = Depends(require_permission("editor")),
):
    result = await _chart(body.model_dump(), f"user:{user.id}")
    return _terminal_response(result)


# Import capabilities to register them at module load
# noinspection PyUnresolvedReferences
from .handlers import capabilities  # noqa: F401, E402
