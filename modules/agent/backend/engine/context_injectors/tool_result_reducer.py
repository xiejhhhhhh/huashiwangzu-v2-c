"""Tool result reducer: compress large tool outputs before they enter the model context.

Upgrade:
- Build tool_call_id → resolved tool name mapping from assistant tool_calls.
- Protect recent N tool results (only max char cap, no semantic summary).
- Semantic summary for known high-volume tool types.
- Local MD5 dedup within a single reduce() call.
- Truncate assistant tool_call arguments (keep JSON valid).
- Strip historical images/base64.
- Enhanced diagnosis counters.

This is a pure function: takes projected messages, returns compressed copies.
Does NOT modify the event store - the original data is preserved in agent_events.
"""

from __future__ import annotations

import hashlib
import json
import logging
import re
from typing import Any

logger = logging.getLogger("v2.agent").getChild("reducer.tool_result")

# ── Default limits ──
_MAX_JSON_CHARS = 2000
_MAX_TEXT_CHARS = 3000
_MAX_LIST_ITEMS = 15
_MAX_HEAD_PERCENT = 0.30
_MAX_TAIL_PERCENT = 0.20
_PROTECTED_RECENT_COUNT = 2
_PROTECTED_RECENT_MAX_CHARS = 8000
_TOOL_ARG_MAX_STR_LEN = 500
_TOOL_ARG_MAX_ARRAY_ITEMS = 5
_TOOL_ARG_MAX_DEPTH = 4
_TOOL_ARG_DEPTH_MARKER = "[参数嵌套过深已省略]"
_IMAGE_PLACEHOLDER = "[图片已省略]"
_DATA_URI_PATTERN = re.compile(r"data:image/[^;]+;base64,[A-Za-z0-9+/=]+", re.IGNORECASE)
_BASE64_IMAGE_PATTERN = re.compile(r"\[data:image/[^;]+;base64,[^\]]*\]", re.IGNORECASE)

# Tool types that produce large, compressible output
_SEMANTIC_SUMMARY_TOOLS: set[str] = {
    "terminal-tools__exec",
    "terminal-tools__run_python",
    "desktop-tools__read_file",
    "desktop-tools__list_files",
    "desktop-tools__search_files",
    "knowledge__search",
    "web-tools__fetch",
    "browser-tools__read_text",
    "media-asr__transcribe_audio",
    "media-asr__transcribe_video",
}
# Keys whose tool results can be huge but still need some summarization
# (these aren't in the semantic list but get the general fallback)


def _resolve_tool_name_from_assistant_messages(projected_messages: list[dict]) -> dict[str, str]:
    """Build a mapping of tool_call_id → resolved tool name.

    For regular tool calls, the name is function.name.
    If function.name == 'skill_use', parse arguments.name as the real tool name
    (e.g. knowledge__search, media-asr__transcribe_video).
    """
    mapping: dict[str, str] = {}
    for msg in projected_messages:
        if msg.get("role") != "assistant":
            continue
        for tc in msg.get("tool_calls") or []:
            tcid = tc.get("id", "") or tc.get("tool_call_id", "") or ""
            fn = tc.get("function", {}) if isinstance(tc, dict) else {}
            fn_name = fn.get("name", "") or tc.get("name", "")
            if not tcid or not fn_name:
                continue
            if fn_name == "skill_use":
                try:
                    args = fn.get("arguments", {})
                    if isinstance(args, str):
                        args = json.loads(args)
                    if isinstance(args, dict):
                        inner_name = args.get("name", "")
                        if inner_name:
                            mapping[tcid] = inner_name
                            continue
                except (json.JSONDecodeError, TypeError):
                    pass
            mapping[tcid] = fn_name
    return mapping


def is_json_content(text: str) -> bool:
    text = text.strip()
    return text.startswith("{") or text.startswith("[")


def _truncate_json(payload: str, max_chars: int = _MAX_JSON_CHARS) -> str:
    if len(payload) <= max_chars:
        return payload
    try:
        data = json.loads(payload)
    except (json.JSONDecodeError, ValueError):
        return _truncate_text_heuristic(payload, max_chars)
    compressed = _compress_json_value(data)
    result = json.dumps(compressed, ensure_ascii=False)
    if len(result) <= max_chars:
        return result
    return _truncate_text_heuristic(payload, max_chars)


def _compress_json_value(value: Any, depth: int = 0) -> Any:
    if depth > 3:
        return "[…]" if isinstance(value, (dict, list)) else value
    if isinstance(value, dict):
        compressed: dict[str, Any] = {}
        for k, v in value.items():
            if isinstance(v, str) and len(v) > 200:
                compressed[k] = v[:120] + "…" + v[-60:]
            elif isinstance(v, list) and len(v) > _MAX_LIST_ITEMS:
                compressed[k] = _compress_json_value(v[: _MAX_LIST_ITEMS], depth + 1)
                compressed[f"{k}_total"] = len(v)
            else:
                compressed[k] = _compress_json_value(v, depth + 1)
        return compressed
    if isinstance(value, list):
        truncated = []
        for item in value:
            truncated.append(_compress_json_value(item, depth + 1))
            if len(truncated) >= _MAX_LIST_ITEMS:
                break
        truncated.append(f"…{len(value)} items total")
        return truncated
    return value


def _truncate_text_heuristic(text: str, max_chars: int = _MAX_TEXT_CHARS) -> str:
    if len(text) <= max_chars:
        return text
    head_len = int(max_chars * _MAX_HEAD_PERCENT)
    tail_len = int(max_chars * _MAX_TAIL_PERCENT)
    tail_len = max(tail_len, min(200, max_chars // 4))
    head = text[:head_len]
    tail = text[-tail_len:]
    return f"{head}\n\n[内容截断：省略 {len(text) - head_len - tail_len} 字符]\n\n{tail}"


def _apply_protected_recent_cap(content: str, max_chars: int = _PROTECTED_RECENT_MAX_CHARS) -> str:
    """Cap recent tool results at max_chars without semantic summarization."""
    if len(content) <= max_chars:
        return content
    head_len = max_chars // 2
    tail_len = max_chars - head_len - 100
    tail_len = max(tail_len, 200)
    head = content[:head_len]
    tail = content[-tail_len:]
    return f"{head}\n\n[结果过长，省略 {len(content) - head_len - tail_len} 字符]\n\n{tail}"


def _semantic_summary(
    content: str,
    tool_name: str,
    max_json_chars: int = _MAX_JSON_CHARS,
    max_text_chars: int = _MAX_TEXT_CHARS,
) -> str:
    """Apply a lightweight semantic-aware summary to known high-volume tool types."""
    if is_json_content(content):
        try:
            data = json.loads(content)
            if isinstance(data, dict):
                # knowledge__search: keep top results
                results = data.get("results") or data.get("data") or data.get("items") or []
                if isinstance(results, list) and len(results) > 5:
                    kept = results[:5]
                    kept.append(f"…共 {len(results)} 条结果")
                    data["results"] = kept
                # file read: keep head/tail
                text_content = data.get("content") or data.get("text") or ""
                if isinstance(text_content, str) and len(text_content) > 2000:
                    data["content"] = text_content[:1000] + "\n…[截断]…" + text_content[-500:]
                return json.dumps(data, ensure_ascii=False, default=str)[:max_json_chars]
        except (json.JSONDecodeError, TypeError):
            pass
    # Plain text: aggressive head/tail
    return _truncate_text_heuristic(content, max_chars=max_text_chars)


def _truncate_tool_argument_value(value: Any, depth: int = 0) -> tuple[Any, int]:
    """Recursively bound a tool argument value and return its truncation count."""
    if depth > _TOOL_ARG_MAX_DEPTH:
        return _TOOL_ARG_DEPTH_MARKER, 1
    if isinstance(value, dict):
        truncated: dict[Any, Any] = {}
        truncation_count = 0
        for key, item in value.items():
            truncated_item, item_count = _truncate_tool_argument_value(item, depth + 1)
            json_key = key if isinstance(key, (str, int, float, bool)) or key is None else str(key)
            truncated[json_key] = truncated_item
            truncation_count += item_count
        return truncated, truncation_count
    if isinstance(value, list):
        truncation_count = 0
        kept_items = value[:_TOOL_ARG_MAX_ARRAY_ITEMS]
        truncated_items: list[Any] = []
        for item in kept_items:
            truncated_item, item_count = _truncate_tool_argument_value(item, depth + 1)
            truncated_items.append(truncated_item)
            truncation_count += item_count
        if len(value) > _TOOL_ARG_MAX_ARRAY_ITEMS:
            truncated_items.append(f"…共{len(value)}项，仅保留前{_TOOL_ARG_MAX_ARRAY_ITEMS}项")
            truncation_count += 1
        return truncated_items, truncation_count
    if isinstance(value, str) and len(value) > _TOOL_ARG_MAX_STR_LEN:
        marker = f"…[省略{len(value) - _TOOL_ARG_MAX_STR_LEN}字符]"
        return value[:_TOOL_ARG_MAX_STR_LEN] + marker, 1
    return value, 0


def _truncate_tool_call_arguments(msg: dict) -> dict:
    """Recursively truncate tool arguments while keeping JSON strings valid."""
    if msg.get("role") != "assistant":
        return msg
    tool_calls = msg.get("tool_calls")
    if not tool_calls:
        return msg
    truncated_calls: list[dict] = []
    args_truncated = 0
    for tc in tool_calls:
        if not isinstance(tc, dict):
            truncated_calls.append(tc)
            continue
        fn = tc.get("function", {})
        if not isinstance(fn, dict):
            truncated_calls.append(tc)
            continue
        original_args = fn.get("arguments", {})
        parsed_args = original_args
        original_was_string = isinstance(original_args, str)
        if original_was_string:
            try:
                parsed_args = json.loads(original_args)
            except (json.JSONDecodeError, TypeError):
                truncated_calls.append(tc)
                continue
        truncated_args, truncation_count = _truncate_tool_argument_value(parsed_args)
        args_truncated += truncation_count
        new_fn = dict(fn)
        if original_was_string and truncation_count == 0:
            new_fn["arguments"] = original_args
        else:
            new_fn["arguments"] = json.dumps(truncated_args, ensure_ascii=False, default=str)
        new_tc = dict(tc)
        new_tc["function"] = new_fn
        truncated_calls.append(new_tc)
    result = dict(msg)
    result["tool_calls"] = truncated_calls
    result["_args_truncated"] = args_truncated
    return result


def _strip_images(msg: dict) -> tuple[dict, bool]:
    """Strip base64 images from a message. Returns (new_msg, was_stripped)."""
    content = msg.get("content", "")
    if not isinstance(content, str):
        return msg, False
    original = content
    content = _DATA_URI_PATTERN.sub(_IMAGE_PLACEHOLDER, content)
    content = _BASE64_IMAGE_PATTERN.sub(_IMAGE_PLACEHOLDER, content)
    if content != original:
        return dict(msg, content=content), True
    return msg, False


def reduce(
    projected_messages: list[dict],
    max_json_chars: int = _MAX_JSON_CHARS,
    max_text_chars: int = _MAX_TEXT_CHARS,
) -> tuple[list[dict], dict]:
    """Compress tool results in projected messages.

    Args:
        projected_messages: list of model messages (from project_to_messages)
        max_json_chars: max chars before JSON compression
        max_text_chars: max chars before text truncation

    Returns:
        (reduced_messages, diagnosis)
    """
    reduced = list(projected_messages)
    compressed_count = 0
    deduped_count = 0
    args_truncated_total = 0
    images_stripped_total = 0
    total_chars_saved = 0
    protected_recent_tool_results = 0

    # Phase 0: Build tool_name mapping from assistant tool_calls
    tool_name_map = _resolve_tool_name_from_assistant_messages(projected_messages)

    # Local MD5 dedup set — scoped to this reduce() call
    seen_hashes: set[str] = set()

    # Identify recent tool result indices (last N tool messages)
    tool_result_indices: list[int] = []
    for i, msg in enumerate(reduced):
        if msg.get("role") == "tool":
            tool_result_indices.append(i)
    protected_indices = set(tool_result_indices[-_PROTECTED_RECENT_COUNT:])

    # Phase 1: Strip images from historical messages (skip recent user msg)
    for i, msg in enumerate(reduced):
        if msg.get("role") == "user":
            continue
        new_msg, stripped = _strip_images(msg)
        if stripped:
            reduced[i] = new_msg
            images_stripped_total += 1

    # Phase 2: Truncate assistant tool_call arguments
    for i, msg in enumerate(reduced):
        if msg.get("role") != "assistant":
            continue
        new_msg = _truncate_tool_call_arguments(msg)
        truncated = new_msg.pop("_args_truncated", 0)
        reduced[i] = new_msg
        if truncated > 0:
            args_truncated_total += truncated

    # Phase 3: Compress tool results
    for i, msg in enumerate(reduced):
        if msg.get("role") != "tool":
            continue
        content = msg.get("content", "")
        if not content or not isinstance(content, str):
            continue

        original_len = len(content)

        # Dedup: MD5 hash of content
        content_hash = hashlib.md5(content.encode("utf-8"), usedforsecurity=False).hexdigest()
        if content_hash in seen_hashes:
            reduced[i] = dict(msg, content="[重复结果已去重]")
            deduped_count += 1
            total_chars_saved += original_len - len("[重复结果已去重]")
            continue
        seen_hashes.add(content_hash)

        tool_call_id = msg.get("tool_call_id", "")
        resolved_name = tool_name_map.get(tool_call_id, msg.get("name", ""))

        if i in protected_indices:
            if original_len > _PROTECTED_RECENT_MAX_CHARS:
                reduced_content = _apply_protected_recent_cap(content)
                reduced[i] = dict(msg, content=reduced_content)
                compressed_count += 1
                protected_recent_tool_results += 1
                total_chars_saved += original_len - len(reduced_content)
            continue

        if resolved_name in _SEMANTIC_SUMMARY_TOOLS:
            reduced_content = _semantic_summary(
                content,
                resolved_name,
                max_json_chars=max_json_chars,
                max_text_chars=max_text_chars,
            )
        else:
            reduced_content = _reduce_tool_content(
                content,
                resolved_name,
                max_json_chars=max_json_chars,
                max_text_chars=max_text_chars,
            )

        if len(reduced_content) < original_len:
            reduced[i] = dict(msg, content=reduced_content)
            compressed_count += 1
            total_chars_saved += original_len - len(reduced_content)

    diagnosis: dict[str, Any] = {
        "tool_results_compressed": compressed_count,
        "tool_results_deduped": deduped_count,
        "tool_args_truncated": args_truncated_total,
        "images_stripped": images_stripped_total,
        "total_chars_saved": total_chars_saved,
        "protected_recent_tool_results": protected_recent_tool_results,
        "total_messages": len(projected_messages),
    }
    return reduced, diagnosis


def _reduce_tool_content(
    content: str,
    tool_name: str = "",
    max_json_chars: int = _MAX_JSON_CHARS,
    max_text_chars: int = _MAX_TEXT_CHARS,
) -> str:
    if not content or len(content) < 500:
        return content
    if is_json_content(content):
        return _truncate_json(content, max_json_chars)
    return _truncate_text_heuristic(content, max_text_chars)
