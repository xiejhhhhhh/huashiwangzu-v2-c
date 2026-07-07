"""Helpers for module capabilities that operate on uploaded files."""
import asyncio
import inspect
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import TypeVar

from app.database import AsyncSessionLocal
from app.models.file import File
from app.services.file_reader import read_uploaded_file, require_positive_file_id, resolve_caller_user_id

T = TypeVar("T")
UploadedFileHandler = Callable[[int, File, Path, str], T | Awaitable[T]]


async def run_uploaded_file_capability(
    params: dict,
    caller: str,
    allowed_exts: set[str],
    handler: UploadedFileHandler[T],
) -> T:
    """Validate caller/file_id, enforce file access, then run the module parser."""
    file_id = require_positive_file_id(params)
    user_id = resolve_caller_user_id(caller)
    async with AsyncSessionLocal() as db:
        file, full_path, ext = await read_uploaded_file(db, file_id, user_id, allowed_exts)

    if inspect.iscoroutinefunction(handler):
        result = handler(file_id, file, full_path, ext)
        return await result
    return await asyncio.to_thread(handler, file_id, file, full_path, ext)
