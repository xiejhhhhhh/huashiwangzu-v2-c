"""FastAPI router for email-parser module.

Parses .eml and .msg email files into unified content blocks.
Extracts headers (from, to, subject, date), body text, and attachments.
"""
import os
from email import message_from_bytes
from email.header import decode_header
from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import AsyncSessionLocal, get_db
from app.middleware.auth import require_permission
from app.models.user import User
from app.schemas.common import ApiResponse
from app.services.module_registry import register_capability

router = APIRouter(prefix="/api/email-parser", tags=["email-parser"])


class ParseRequest(BaseModel):
    file_id: int


def _resolve_user_id(caller: str) -> int:
    from app.core.exceptions import PermissionDenied
    try:
        prefix, raw_id = caller.split(":", 1)
        if prefix == "user":
            return int(raw_id)
    except (TypeError, ValueError):
        pass
    raise PermissionDenied("Invalid caller")


def _decode_email_header(value: str) -> str:
    if not value:
        return ""
    parts = decode_header(value)
    result = []
    for part, encoding in parts:
        if isinstance(part, bytes):
            try:
                result.append(part.decode(encoding or "utf-8", errors="replace"))
            except (LookupError, UnicodeDecodeError):
                result.append(part.decode("utf-8", errors="replace"))
        else:
            result.append(str(part))
    return " ".join(result)


def _extract_body(part) -> str:
    payload = part.get_payload(decode=True)
    if payload:
        content_type = part.get_content_type()
        if content_type == "text/plain":
            try:
                return payload.decode("utf-8", errors="replace")
            except (UnicodeDecodeError, LookupError):
                return payload.decode("latin-1", errors="replace")
        elif content_type == "text/html":
            try:
                text = payload.decode("utf-8", errors="replace")
            except (UnicodeDecodeError, LookupError):
                text = payload.decode("latin-1", errors="replace")
            import re
            text = re.sub(r"<[^>]+>", "", text)
            text = re.sub(r"\s+", " ", text).strip()
            return text
    return ""


async def _parse(params: dict, caller: str) -> dict:
    file_id = int(params.get("file_id", 0))
    if file_id <= 0:
        raise ValueError("file_id must be a positive integer")

    from app.config import get_settings
    from app.core.exceptions import NotFound, ValidationError, AppException
    from app.services.file_service import check_file_access
    from pathlib import Path

    allowed = {"eml", "msg"}
    user_id = _resolve_user_id(caller)
    async with AsyncSessionLocal() as db:
        file = await check_file_access(db, file_id, user_id)
        ext = (file.extension or "").lower()
        if ext not in allowed:
            raise ValidationError(f"Unsupported format '{ext}'. Allowed: eml, msg")
        if not file.storage_path:
            raise NotFound("File storage path is empty")
        upload_root = Path(get_settings().UPLOAD_DIR).resolve()
        full_path = (upload_root / file.storage_path).resolve()
        if os.path.commonpath([str(upload_root), str(full_path)]) != str(upload_root):
            raise AppException("Unsafe file storage path", status_code=400)
        if not full_path.exists() or not full_path.is_file():
            raise NotFound("File on disk not found")

        raw = full_path.read_bytes()
        blocks = []
        resource_counter = 0
        resources = []

        if ext == "msg":
            try:
                import extract_msg
                msg = extract_msg.Message(full_path)
                msg.message
                blocks.append({"type": "段落", "text": f"发件人：{msg.sender or '未知'}", "page": None, "resource_ref": None})
                blocks.append({"type": "段落", "text": f"收件人：{msg.to or '未知'}", "page": None, "resource_ref": None})
                blocks.append({"type": "段落", "text": f"主题：{msg.subject or '(无主题)'}", "page": None, "resource_ref": None})
                blocks.append({"type": "段落", "text": f"日期：{msg.date or '未知'}", "page": None, "resource_ref": None})
                body = msg.body or ""
                if body.strip():
                    blocks.append({"type": "段落", "text": body.strip(), "page": None, "resource_ref": None})
                else:
                    blocks.append({"type": "段落", "text": "(邮件无文本正文)", "page": None, "resource_ref": None})
            except ImportError:
                raise ValidationError("MSG parsing requires extract-msg library")
            except Exception as e:
                raise ValidationError(f"Failed to parse MSG file: {e}")
        else:
            try:
                msg = message_from_bytes(raw)
            except Exception as e:
                raise ValidationError(f"Failed to parse EML file: {e}")

            headers = {
                "from": _decode_email_header(msg.get("From", "")),
                "to": _decode_email_header(msg.get("To", "")),
                "cc": _decode_email_header(msg.get("Cc", "")),
                "subject": _decode_email_header(msg.get("Subject", "")),
                "date": msg.get("Date", ""),
            }

            blocks.append({"type": "标题", "text": f"邮件：{headers['subject'] or '(无主题)'}", "page": None, "resource_ref": None})
            header_text = (
                f"发件人：{headers['from'] or '未知'}\n"
                f"收件人：{headers['to'] or '未知'}\n"
            )
            if headers["cc"]:
                header_text += f"抄送：{headers['cc']}\n"
            header_text += f"日期：{headers['date'] or '未知'}"
            blocks.append({"type": "段落", "text": header_text, "page": None, "resource_ref": None})

            if msg.is_multipart():
                body_parts = []
                for part in msg.walk():
                    content_disposition = str(part.get("Content-Disposition", ""))
                    if "attachment" in content_disposition.lower():
                        resource_counter += 1
                        filename = part.get_filename() or f"attachment_{resource_counter}"
                        resources.append({
                            "id": resource_counter,
                            "type": "附件",
                            "file_storage_id": None,
                            "text_desc": _decode_email_header(filename),
                        })
                        continue
                    body_text = _extract_body(part)
                    if body_text.strip():
                        body_parts.append(body_text.strip())
                if body_parts:
                    blocks.append({"type": "段落", "text": "\n\n".join(body_parts), "page": None, "resource_ref": None})
                else:
                    blocks.append({"type": "段落", "text": "(邮件无文本正文)", "page": None, "resource_ref": None})
            else:
                body = _extract_body(msg)
                if body.strip():
                    blocks.append({"type": "段落", "text": body.strip(), "page": None, "resource_ref": None})

    return {
        "file_id": file_id,
        "format": "email",
        "blocks": blocks,
        "resources": resources,
    }


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
