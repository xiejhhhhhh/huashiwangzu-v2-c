"""Input validation helpers for docs-open contracts."""

from __future__ import annotations

import re
from typing import Any

from app.core.exceptions import AppException

CLIENT_ID_PATTERN = re.compile(r"^[A-Za-z0-9._-]{1,64}$")
MAX_SCOPE_DOC_IDS = 100
MAX_TOKEN_EXPIRY_HOURS = 24
ALLOWED_CREATE_TYPES = {
    "txt",
    "md",
    "json",
    "yaml",
    "yml",
    "xml",
    "ini",
    "cfg",
    "log",
    "csv",
    "docx",
    "xlsx",
    "pptx",
    "pdf",
}


def _bad_request(message: str) -> AppException:
    return AppException(message, status_code=400)


def normalize_positive_int(value: Any, field_name: str) -> int:
    if isinstance(value, bool):
        raise _bad_request(f"{field_name} must be a positive integer")
    try:
        parsed = int(value)
    except (TypeError, ValueError) as exc:
        raise _bad_request(f"{field_name} must be a positive integer") from exc
    if parsed <= 0:
        raise _bad_request(f"{field_name} must be a positive integer")
    return parsed


def normalize_client_id(value: Any) -> str:
    client_id = str(value or "").strip()
    if not CLIENT_ID_PATTERN.fullmatch(client_id):
        raise _bad_request("client_id must be 1-64 characters: letters, digits, dot, underscore or hyphen")
    return client_id


def normalize_expiry_hours(value: Any) -> int:
    expiry_hours = normalize_positive_int(value, "expiry_hours")
    if expiry_hours > MAX_TOKEN_EXPIRY_HOURS:
        raise _bad_request(f"expiry_hours must be <= {MAX_TOKEN_EXPIRY_HOURS}")
    return expiry_hours


def normalize_doc_id_list(value: Any, field_name: str) -> list[int]:
    if not isinstance(value, list) or len(value) == 0:
        raise _bad_request(f"scope.{field_name} must be a non-empty list")
    if len(value) > MAX_SCOPE_DOC_IDS:
        raise _bad_request(f"scope.{field_name} cannot contain more than {MAX_SCOPE_DOC_IDS} documents")

    result: list[int] = []
    seen: set[int] = set()
    for item in value:
        doc_id = normalize_positive_int(item, f"scope.{field_name}[]")
        if doc_id not in seen:
            result.append(doc_id)
            seen.add(doc_id)
    return result


def normalize_token_scope(scope: Any) -> dict[str, list[int]]:
    if not isinstance(scope, dict):
        raise _bad_request("scope must be an object")

    allowed_keys = {"doc_ids", "edit_doc_ids"}
    unknown_keys = set(scope.keys()) - allowed_keys
    if unknown_keys:
        raise _bad_request(f"unsupported scope keys: {', '.join(sorted(unknown_keys))}")

    normalized: dict[str, list[int]] = {}
    if "doc_ids" in scope:
        normalized["doc_ids"] = normalize_doc_id_list(scope["doc_ids"], "doc_ids")
    if "edit_doc_ids" in scope:
        normalized["edit_doc_ids"] = normalize_doc_id_list(scope["edit_doc_ids"], "edit_doc_ids")

    if not normalized:
        raise _bad_request("scope must include doc_ids or edit_doc_ids")
    return normalized


def normalize_mode(value: Any) -> str:
    mode = str(value or "view").strip().lower()
    if mode in {"view", "read"}:
        return "view"
    if mode == "edit":
        return "edit"
    raise _bad_request("mode must be 'view' or 'edit'")


def access_mode_for_mode(mode: str) -> str:
    return "edit" if normalize_mode(mode) == "edit" else "read"


def normalize_doc_type(value: Any) -> str:
    doc_type = str(value or "txt").strip().lower().lstrip(".")
    if doc_type == "plain":
        doc_type = "txt"
    if doc_type not in ALLOWED_CREATE_TYPES:
        raise _bad_request(f"doc_type must be one of: {', '.join(sorted(ALLOWED_CREATE_TYPES))}")
    return doc_type


def normalize_title(value: Any) -> str:
    title = str(value or "").strip()
    if not title:
        raise _bad_request("title is required")
    if len(title) > 255:
        raise _bad_request("title must be <= 255 characters")
    if "\x00" in title or "/" in title or "\\" in title:
        raise _bad_request("title cannot contain path separators")
    return title
