"""Exact text patch helpers for the project toolkit MCP server."""

from __future__ import annotations

import difflib
import hashlib
import os
import time
from pathlib import Path
from typing import Any


class QuickFixError(ValueError):
    """Raised when a requested patch is unsafe or ambiguous."""


_BLOCKED_PARTS = {
    ".git",
    "__pycache__",
    "node_modules",
    ".venv",
    "venv",
    "_废弃",
    "后端",
    "脚本",
    "部署",
}


def quick_fix_preview(
    repo_root: Path,
    path: str,
    old_text: str,
    new_text: str,
    start_line: int | None = None,
    end_line: int | None = None,
    expected_old_text_sha256: str = "",
) -> dict[str, Any]:
    """Validate an exact replacement and return the diff without writing."""

    target = _resolve_target(repo_root, path)
    original = _read_text(target)
    match = _find_unique_match(
        original,
        old_text,
        start_line=start_line,
        end_line=end_line,
        expected_old_text_sha256=expected_old_text_sha256,
    )
    patched = original[: match["start_offset"]] + new_text + original[match["end_offset"] :]
    return _build_result(
        repo_root=repo_root,
        target=target,
        original=original,
        patched=patched,
        match=match,
        applied=False,
    )


def quick_fix_patch(
    repo_root: Path,
    path: str,
    old_text: str,
    new_text: str,
    start_line: int | None = None,
    end_line: int | None = None,
    expected_old_text_sha256: str = "",
) -> dict[str, Any]:
    """Apply an exact replacement after the same validation as preview."""

    target = _resolve_target(repo_root, path)
    original = _read_text(target)
    match = _find_unique_match(
        original,
        old_text,
        start_line=start_line,
        end_line=end_line,
        expected_old_text_sha256=expected_old_text_sha256,
    )
    patched = original[: match["start_offset"]] + new_text + original[match["end_offset"] :]
    _atomic_write_text(target, patched)
    return _build_result(
        repo_root=repo_root,
        target=target,
        original=original,
        patched=patched,
        match=match,
        applied=True,
    )


def _resolve_target(repo_root: Path, raw_path: str) -> Path:
    if not raw_path or not raw_path.strip():
        raise QuickFixError("path is required")

    repo_root = repo_root.resolve()
    candidate = Path(raw_path).expanduser()
    target = candidate.resolve() if candidate.is_absolute() else (repo_root / candidate).resolve()

    try:
        rel = target.relative_to(repo_root)
    except ValueError as exc:
        raise QuickFixError("target path must stay inside repo root") from exc

    if any(part in _BLOCKED_PARTS for part in rel.parts):
        raise QuickFixError(f"target path is blocked by scan/edit boundary: {rel}")
    if target.suffix == ".pyc":
        raise QuickFixError("compiled Python files cannot be patched")
    if not target.exists():
        raise QuickFixError(f"target file does not exist: {rel}")
    if not target.is_file():
        raise QuickFixError(f"target is not a file: {rel}")
    return target


def _read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except UnicodeDecodeError as exc:
        raise QuickFixError("target file is not valid UTF-8") from exc


def _find_unique_match(
    text: str,
    old_text: str,
    start_line: int | None,
    end_line: int | None,
    expected_old_text_sha256: str,
) -> dict[str, Any]:
    if not old_text:
        raise QuickFixError("old_text must not be empty")

    old_hash = _sha256(old_text)
    expected = expected_old_text_sha256.strip().lower()
    if expected and expected != old_hash:
        raise QuickFixError(
            f"old_text sha256 mismatch: expected {expected}, got {old_hash}"
        )

    ranges = _line_ranges(text)
    line_window = _normalize_line_window(ranges, start_line, end_line)
    matches = _all_occurrences(text, old_text)
    if line_window:
        range_start, range_end = line_window
        matches = [
            item
            for item in matches
            if item[0] >= range_start and item[1] <= range_end
        ]

    if not matches:
        detail: dict[str, Any] = {"match_count": 0, "old_text_sha256": old_hash}
        if line_window:
            detail["selected_text_sha256"] = _sha256(text[line_window[0] : line_window[1]])
            detail["selected_text_preview"] = text[line_window[0] : line_window[1]][:500]
        raise QuickFixError("old_text was not found uniquely: " + repr(detail))

    if len(matches) > 1:
        line_spans = [
            {
                "start_line": _line_for_offset(text, start),
                "end_line": _line_for_offset(text, max(start, end - 1)),
            }
            for start, end in matches[:20]
        ]
        raise QuickFixError(
            "old_text is ambiguous; provide start_line/end_line: "
            + repr({"match_count": len(matches), "matches": line_spans})
        )

    start, end = matches[0]
    return {
        "start_offset": start,
        "end_offset": end,
        "start_line": _line_for_offset(text, start),
        "end_line": _line_for_offset(text, max(start, end - 1)),
        "old_text_sha256": old_hash,
    }


def _normalize_line_window(
    ranges: list[tuple[int, int]],
    start_line: int | None,
    end_line: int | None,
) -> tuple[int, int] | None:
    if start_line is None and end_line is None:
        return None
    if start_line is None or end_line is None:
        raise QuickFixError("start_line and end_line must be provided together")
    start_line = _coerce_line_number(start_line, "start_line")
    end_line = _coerce_line_number(end_line, "end_line")
    if start_line < 1 or end_line < start_line:
        raise QuickFixError("invalid line range")
    if end_line > len(ranges):
        raise QuickFixError(f"line range exceeds file length: {len(ranges)} lines")
    return ranges[start_line - 1][0], ranges[end_line - 1][1]


def _coerce_line_number(value: int | float, name: str) -> int:
    if isinstance(value, bool):
        raise QuickFixError(f"{name} must be an integer")
    if isinstance(value, float):
        if not value.is_integer():
            raise QuickFixError(f"{name} must be an integer")
        return int(value)
    if not isinstance(value, int):
        raise QuickFixError(f"{name} must be an integer")
    return value


def _line_ranges(text: str) -> list[tuple[int, int]]:
    lines = text.splitlines(keepends=True)
    if not lines:
        return [(0, 0)]
    ranges: list[tuple[int, int]] = []
    offset = 0
    for line in lines:
        next_offset = offset + len(line)
        ranges.append((offset, next_offset))
        offset = next_offset
    return ranges


def _all_occurrences(text: str, needle: str) -> list[tuple[int, int]]:
    matches: list[tuple[int, int]] = []
    start = 0
    while True:
        index = text.find(needle, start)
        if index < 0:
            break
        matches.append((index, index + len(needle)))
        start = index + max(1, len(needle))
    return matches


def _line_for_offset(text: str, offset: int) -> int:
    if offset <= 0:
        return 1
    return text.count("\n", 0, offset) + 1


def _build_result(
    repo_root: Path,
    target: Path,
    original: str,
    patched: str,
    match: dict[str, Any],
    applied: bool,
) -> dict[str, Any]:
    rel = str(target.relative_to(repo_root.resolve()))
    diff = "".join(
        difflib.unified_diff(
            original.splitlines(keepends=True),
            patched.splitlines(keepends=True),
            fromfile=f"a/{rel}",
            tofile=f"b/{rel}",
        )
    )
    return {
        "success": True,
        "applied": applied,
        "path": rel,
        "start_line": match["start_line"],
        "end_line": match["end_line"],
        "old_text_sha256": match["old_text_sha256"],
        "file_sha256_before": _sha256(original),
        "file_sha256_after": _sha256(patched),
        "diff": diff,
    }


def _atomic_write_text(path: Path, text: str) -> None:
    stat = path.stat()
    tmp = path.with_name(f".{path.name}.tmp.{os.getpid()}.{int(time.time() * 1000)}")
    try:
        tmp.write_text(text, encoding="utf-8")
        os.chmod(tmp, stat.st_mode)
        tmp.replace(path)
    finally:
        try:
            tmp.unlink()
        except FileNotFoundError:
            pass


def _sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()
