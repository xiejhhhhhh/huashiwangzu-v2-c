from pathlib import Path
from sqlalchemy.ext.asyncio import AsyncSession
from app.models.file import File
from app.core.exceptions import NotFound, PermissionDenied, AppException
from app.config import get_settings

settings = get_settings()

TEXT_EXTENSIONS = {
    'txt', 'md', 'json', 'csv', 'log', 'xml', 'yaml', 'yml',
    'ini', 'cfg', 'conf', 'env', 'sql', 'toml',
    'php', 'js', 'ts', 'jsx', 'tsx', 'css', 'scss', 'less',
    'html', 'htm', 'vue',
    'py', 'java', 'go', 'rs', 'kt', 'c', 'cpp', 'h', 'hpp', 'cs', 'rb',
    'sh', 'bash', 'zsh', 'ps1', 'bat', 'cmd',
    'pl', 'lua', 'r', 'dart', 'dockerfile', 'makefile', 'gradle',
}
IMAGE_EXTS = {"jpg", "jpeg", "png", "gif", "webp", "bmp", "svg", "ico"}
AUDIO_EXTS = {"mp3", "wav", "aac", "ogg", "flac", "m4a"}
VIDEO_EXTS = {"mp4", "webm", "mov", "avi", "mkv", "flv"}
OFFICE_EXTS = {"doc", "docx", "xls", "xlsx", "ppt", "pptx"}

SIZE_LIMITS = {
    "image": 20 * 1024 * 1024,
    "pdf": 50 * 1024 * 1024,
    "text": 5 * 1024 * 1024,
    "video": 500 * 1024 * 1024,
    "audio": 200 * 1024 * 1024,
    "default": 100 * 1024 * 1024,
}
MAX_TEXT_PREVIEW = settings.MAX_PREVIEW_SIZE


async def preview_file(db: AsyncSession, file_id: int, owner_id: int) -> dict:
    file = await db.get(File, file_id)
    if not file or file.deleted:
        raise NotFound("File not found or deleted")
    if file.owner_id != owner_id:
        raise PermissionDenied("No permission to preview this file")

    ext = (file.extension or "").lower()
    safe_path = _resolve_storage_path(file)
    if not safe_path:
        raise NotFound("File on disk not found")

    size_limit = _get_size_limit(ext)
    if file.size > size_limit:
        limit_mb = round(size_limit / 1024 / 1024, 1)
        type_name = _get_type_name(ext)
        raise AppException(
            f"{type_name} file exceeds {limit_mb}MB, cannot preview inline",
            status_code=413,
        )

    if ext in OFFICE_EXTS:
        raise AppException("Office files are not supported for online preview", status_code=400)

    if ext in TEXT_EXTENSIONS:
        content = _read_text_content(safe_path)
        return {
            "content": content,
            "format": ext,
            "file_info": {
                "id": file.id,
                "name": file.name,
                "extension": file.extension,
                "size": file.size,
            },
        }

    mime_map = _get_mime_map()
    mime_type = mime_map.get(ext, "application/octet-stream")
    return {
        "mime_type": mime_type,
        "file_info": {
            "id": file.id,
            "name": file.name,
            "extension": file.extension,
            "size": file.size,
        },
        "download_url": f"/api/files/download/{file.id}",
    }


def _resolve_storage_path(file: File) -> Path | None:
    if not file.storage_path:
        return None
    full_path = Path(settings.UPLOAD_DIR) / file.storage_path
    return full_path if full_path.exists() else None


def _read_text_content(path: Path) -> str:
    if not path.exists() or not path.is_file():
        raise AppException("File not readable", status_code=500)
    size = path.stat().st_size
    read_len = min(size, MAX_TEXT_PREVIEW)
    truncated = size > read_len
    content = path.read_bytes()[:read_len]
    try:
        text = content.decode("utf-8")
    except UnicodeDecodeError:
        try:
            text = content.decode("gbk")
        except UnicodeDecodeError:
            text = content.decode("utf-8", errors="replace")
    if truncated:
        text += "\n\n--- File too long, showing first 1MB ---"
    return text


def _get_mime_map() -> dict:
    return {
        "pdf": "application/pdf",
        "png": "image/png", "jpg": "image/jpeg", "jpeg": "image/jpeg",
        "gif": "image/gif", "svg": "image/svg+xml", "webp": "image/webp",
        "bmp": "image/bmp", "ico": "image/x-icon",
        "mp4": "video/mp4", "webm": "video/webm",
        "mp3": "audio/mpeg", "wav": "audio/wav",
    }


def _get_size_limit(ext: str) -> int:
    ext_lower = ext.lower()
    if ext_lower in IMAGE_EXTS:
        return SIZE_LIMITS["image"]
    if ext_lower == "pdf":
        return SIZE_LIMITS["pdf"]
    if ext_lower in AUDIO_EXTS:
        return SIZE_LIMITS["audio"]
    if ext_lower in VIDEO_EXTS:
        return SIZE_LIMITS["video"]
    if ext_lower in TEXT_EXTENSIONS:
        return SIZE_LIMITS["text"]
    return SIZE_LIMITS["default"]


def _get_type_name(ext: str) -> str:
    ext_lower = ext.lower()
    if ext_lower in IMAGE_EXTS:
        return "Image"
    if ext_lower == "pdf":
        return "PDF"
    if ext_lower in OFFICE_EXTS:
        return "Office"
    if ext_lower in AUDIO_EXTS:
        return "Audio"
    if ext_lower in VIDEO_EXTS:
        return "Video"
    if ext_lower in TEXT_EXTENSIONS:
        return "Text"
    return "File"
