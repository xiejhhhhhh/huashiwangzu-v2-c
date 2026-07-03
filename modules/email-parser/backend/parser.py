from __future__ import annotations

import base64
import html
from email import policy
from email.header import decode_header
from email.message import Message
from email.parser import BytesParser
from html.parser import HTMLParser
from pathlib import Path
from typing import Any


class EmailParseError(ValueError):
    """Raised when the input is not a parseable email file."""


class _HtmlTextExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self._chunks: list[str] = []
        self._skip_depth = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag.lower() in {"script", "style"}:
            self._skip_depth += 1
        elif tag.lower() in {"br", "p", "div", "tr", "li"}:
            self._chunks.append("\n")

    def handle_endtag(self, tag: str) -> None:
        if tag.lower() in {"script", "style"} and self._skip_depth:
            self._skip_depth -= 1
        elif tag.lower() in {"p", "div", "tr", "li"}:
            self._chunks.append("\n")

    def handle_data(self, data: str) -> None:
        if self._skip_depth:
            return
        text = data.strip()
        if text:
            self._chunks.append(text)

    def get_text(self) -> str:
        lines = [" ".join(line.split()) for line in "".join(self._chunks).splitlines()]
        return "\n".join(line for line in lines if line).strip()


def parse_email_file(file_id: int, full_path: Path, ext: str) -> dict[str, Any]:
    if ext == "eml":
        return _parse_eml_file(file_id, full_path)
    if ext == "msg":
        return _parse_msg_file(file_id, full_path)
    raise EmailParseError(f"Unsupported email format: {ext}")


def _parse_eml_file(file_id: int, full_path: Path) -> dict[str, Any]:
    raw = full_path.read_bytes()
    if not raw.strip():
        raise EmailParseError("Email file is empty")

    try:
        msg = BytesParser(policy=policy.default).parsebytes(raw)
    except Exception as exc:
        raise EmailParseError(f"Failed to parse EML file: {exc}") from exc

    headers = _extract_headers(msg)
    if not any(headers.values()):
        raise EmailParseError("Input does not look like a structured email message")

    body_text, resources, attachment_blocks = _extract_eml_payload(msg)

    blocks = _build_header_blocks(headers)
    if body_text:
        blocks.append({"type": "paragraph", "text": body_text, "page": None, "resource_ref": None})
    elif resources:
        blocks.append({"type": "paragraph", "text": "(email has no text body)", "page": None, "resource_ref": None})
    blocks.extend(attachment_blocks)

    return {
        "file_id": file_id,
        "format": "email",
        "blocks": blocks,
        "resources": resources,
        "resource_diagnostics": [],
    }


def _parse_msg_file(file_id: int, full_path: Path) -> dict[str, Any]:
    try:
        import extract_msg
    except ImportError as exc:
        raise EmailParseError("MSG parsing requires extract-msg library") from exc

    msg_obj = None
    try:
        msg_obj = extract_msg.Message(str(full_path))
        headers = {
            "from": str(getattr(msg_obj, "sender", "") or ""),
            "to": str(getattr(msg_obj, "to", "") or ""),
            "cc": str(getattr(msg_obj, "cc", "") or ""),
            "subject": str(getattr(msg_obj, "subject", "") or ""),
            "date": str(getattr(msg_obj, "date", "") or ""),
        }
        body_text = str(getattr(msg_obj, "body", "") or "").strip()
        if not any(headers.values()):
            raise EmailParseError("Input does not look like a structured MSG email")

        if not body_text:
            html_body = getattr(msg_obj, "htmlBody", "") or ""
            if isinstance(html_body, bytes):
                html_body = _decode_bytes(html_body)
            body_text = _html_to_text(str(html_body))

        resources, attachment_blocks = _extract_msg_attachments(msg_obj)

        blocks = _build_header_blocks(headers)
        if body_text:
            blocks.append({"type": "paragraph", "text": body_text, "page": None, "resource_ref": None})
        elif resources:
            blocks.append({"type": "paragraph", "text": "(email has no text body)", "page": None, "resource_ref": None})
        blocks.extend(attachment_blocks)
        return {
            "file_id": file_id,
            "format": "email",
            "blocks": blocks,
            "resources": resources,
            "resource_diagnostics": [],
        }
    except EmailParseError:
        raise
    except Exception as exc:
        raise EmailParseError(f"Failed to parse MSG file: {exc}") from exc
    finally:
        close = getattr(msg_obj, "close", None)
        if callable(close):
            close()


def _extract_headers(msg: Message) -> dict[str, str]:
    return {
        "from": _decode_header_value(msg.get("From", "")),
        "to": _decode_header_value(msg.get("To", "")),
        "cc": _decode_header_value(msg.get("Cc", "")),
        "subject": _decode_header_value(msg.get("Subject", "")),
        "date": str(msg.get("Date", "") or ""),
    }


def _build_header_blocks(headers: dict[str, str]) -> list[dict[str, Any]]:
    subject = headers.get("subject") or "(no subject)"
    header_lines = [
        f"From: {headers.get('from') or 'unknown'}",
        f"To: {headers.get('to') or 'unknown'}",
    ]
    if headers.get("cc"):
        header_lines.append(f"Cc: {headers['cc']}")
    header_lines.append(f"Date: {headers.get('date') or 'unknown'}")
    return [
        {"type": "heading", "text": f"Email: {subject}", "page": None, "resource_ref": None},
        {"type": "paragraph", "text": "\n".join(header_lines), "page": None, "resource_ref": None},
    ]


def _extract_eml_payload(msg: Message) -> tuple[str, list[dict[str, Any]], list[dict[str, Any]]]:
    plain_parts: list[str] = []
    html_parts: list[str] = []
    resources: list[dict[str, Any]] = []
    attachment_blocks: list[dict[str, Any]] = []

    parts = list(msg.walk()) if msg.is_multipart() else [msg]
    for part in parts:
        if part.is_multipart():
            continue

        filename = _decode_header_value(part.get_filename() or "")
        disposition = (part.get_content_disposition() or "").lower()
        content_type = part.get_content_type()
        is_attachment = disposition == "attachment" or bool(filename)
        if is_attachment:
            resource_id = len(resources) + 1
            payload = part.get_payload(decode=True) or b""
            resource = _build_resource(
                resource_id=resource_id,
                filename=filename or f"attachment_{resource_id}",
                mime_type=content_type,
                data=payload,
            )
            resources.append(resource)
            attachment_blocks.append({
                "type": "paragraph",
                "text": f"Attachment: {resource['filename']}",
                "page": None,
                "resource_ref": resource_id,
            })
            continue

        body = _decode_part_text(part)
        if not body:
            continue
        if content_type == "text/plain":
            plain_parts.append(body)
        elif content_type == "text/html":
            html_text = _html_to_text(body)
            if html_text:
                html_parts.append(html_text)

    body_text = "\n\n".join(part.strip() for part in plain_parts if part.strip()).strip()
    if not body_text:
        body_text = "\n\n".join(part.strip() for part in html_parts if part.strip()).strip()
    return body_text, resources, attachment_blocks


def _extract_msg_attachments(msg_obj: object) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    resources: list[dict[str, Any]] = []
    attachment_blocks: list[dict[str, Any]] = []
    for attachment in getattr(msg_obj, "attachments", []) or []:
        resource_id = len(resources) + 1
        filename = (
            getattr(attachment, "longFilename", None)
            or getattr(attachment, "shortFilename", None)
            or getattr(attachment, "filename", None)
            or f"attachment_{resource_id}"
        )
        data = getattr(attachment, "data", b"") or b""
        if isinstance(data, str):
            data = data.encode("utf-8")
        mime_type = getattr(attachment, "mimetype", None) or "application/octet-stream"
        resource = _build_resource(
            resource_id=resource_id,
            filename=str(filename),
            mime_type=str(mime_type),
            data=data,
        )
        resources.append(resource)
        attachment_blocks.append({
            "type": "paragraph",
            "text": f"Attachment: {resource['filename']}",
            "page": None,
            "resource_ref": resource_id,
        })
    return resources, attachment_blocks


def _build_resource(resource_id: int, filename: str, mime_type: str, data: bytes) -> dict[str, Any]:
    resource_type = "image" if mime_type.startswith("image/") else "attachment"
    description = f"Email attachment: {filename}"
    return {
        "id": resource_id,
        "type": resource_type,
        "resource_type": resource_type,
        "mime_type": mime_type or "application/octet-stream",
        "filename": filename,
        "description": description,
        "file_storage_id": None,
        "text_desc": description,
        "_bytes_b64": base64.b64encode(data).decode("ascii") if data else "",
    }


def _decode_header_value(value: str | None) -> str:
    if not value:
        return ""
    parts = decode_header(value)
    result = []
    for part, encoding in parts:
        if isinstance(part, bytes):
            result.append(_decode_bytes(part, encoding))
        else:
            result.append(str(part))
    return " ".join(result).strip()


def _decode_part_text(part: Message) -> str:
    payload = part.get_payload(decode=True)
    if payload is None:
        raw_payload = part.get_payload()
        if isinstance(raw_payload, str):
            return raw_payload.strip()
        return ""
    return _decode_bytes(payload, part.get_content_charset()).strip()


def _decode_bytes(data: bytes, charset: str | None = None) -> str:
    encodings = [charset, "utf-8", "gb18030", "latin-1"]
    for encoding in encodings:
        if not encoding:
            continue
        try:
            return data.decode(encoding, errors="replace")
        except (LookupError, UnicodeDecodeError):
            continue
    return data.decode("utf-8", errors="replace")


def _html_to_text(value: str) -> str:
    parser = _HtmlTextExtractor()
    try:
        parser.feed(value)
        parser.close()
        return html.unescape(parser.get_text())
    except Exception:
        return html.unescape(value).strip()
