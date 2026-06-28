"""ContentGate — unified content cleaning and classification for all model output paths.

All agent model output (tokens, content, thinking, final summary, inline tool calls)
must pass through ContentGate before being displayed to the user or persisted.

This replaces ad-hoc cleaning spread across model_client.py, stream_emitter.py,
tool_loop_runtime.py, and task_sink.py with a single gate.
"""

from __future__ import annotations

import json
import logging
import re
import uuid

logger = logging.getLogger("v2.agent").getChild("runtime.content_gate")

_SEARCH_INTENT_MARKERS = (
    "我帮你联网查",
    "我来联网查",
    "我帮你搜索",
    "我来搜索",
    "我查一下",
    "我搜一下",
    "联网查一下",
    "搜索一下最新",
)

TOOL_INTENT_RETRY_MESSAGE = (
    "Your previous draft promised to search, browse, read files, or use a tool, "
    "but it did not emit any tool call. Regenerate this turn now: if external "
    "information is needed, emit the appropriate tool call; otherwise answer "
    "directly without saying you will go search or check later."
)


class ContentGateResult:
    """Result of processing model output through ContentGate."""

    __slots__ = (
        "raw_text",
        "normalized_text",
        "clean_text",
        "inline_tool_calls",
        "extracted_tool_calls_count",
        "has_visible_text",
        "is_empty",
        "is_xml_only",
        "unfinished_tool_intent",
        "blocked_reason",
    )

    def __init__(self, raw_text: str) -> None:
        self.raw_text = raw_text
        self.normalized_text = ""
        self.clean_text = ""
        self.inline_tool_calls: list[dict] = []
        self.extracted_tool_calls_count: int = 0
        self.has_visible_text: bool = False
        self.is_empty: bool = True
        self.is_xml_only: bool = False
        self.unfinished_tool_intent: bool = False
        self.blocked_reason: str | None = None

    def __repr__(self) -> str:
        return (
            f"ContentGateResult("
            f"raw_len={len(self.raw_text)}, "
            f"clean_len={len(self.clean_text)}, "
            f"tool_calls={self.extracted_tool_calls_count}, "
            f"has_text={self.has_visible_text}, "
            f"empty={self.is_empty}, "
            f"xml_only={self.is_xml_only}, "
            f"unfinished={self.unfinished_tool_intent})"
        )


def _normalize_inline_markup(content: str) -> str:
    """Normalize DSML, full-width variants, and unusual prefixes to standard XML."""
    normalized = content
    # DSML prefix variants seen in DeepSeek output
    normalized = normalized.replace("<｜｜DSML｜｜", "<")
    normalized = normalized.replace("</｜｜DSML｜｜", "</")
    normalized = normalized.replace("<｜｜DSML｜<", "<")
    normalized = normalized.replace("</｜｜DSML｜<", "</")
    # ASCII shorthand used by tests / copied output
    normalized = normalized.replace("<DSML>", "")
    normalized = normalized.replace("</DSML>", "")
    # Full-width and ASCII vertical-bar tag prefixes
    for tag in ("tool_call", "tool_calls", "invoke", "parameter"):
        normalized = normalized.replace(f"<｜{tag}", f"<{tag}")
        normalized = normalized.replace(f"</｜{tag}", f"</{tag}")
        normalized = normalized.replace(f"</｜{tag}", f"</{tag}")
        normalized = normalized.replace(f"｜{tag}", f"<{tag}")
        normalized = normalized.replace(f"</|{tag}", f"</{tag}")
        normalized = normalized.replace(f"|{tag}", f"<{tag}")
    return normalized


def _strip_tool_call_containers(content: str) -> str:
    """Remove bare tool_call/tool_calls wrapper tags."""
    return re.sub(
        r'</?\w*:?tool_calls?\s*>',
        '', content, flags=re.IGNORECASE | re.DOTALL,
    )


def _strip_internal_success_sections(content: str) -> str:
    """Remove internal learning snippets that should not be user-visible."""
    cleaned = re.sub(
        r'<p>\s*<strong>\s*最佳路径总结[:：]\s*</strong>[\s\S]*?</p>',
        '',
        content,
        flags=re.IGNORECASE,
    )
    cleaned = re.sub(
        r'(?:^|\n)\s*(?:\*\*)?最佳路径总结[:：](?:\*\*)?[\s\S]*?(?=\n\s*📎\s*来源[:：]|\n\s*#{1,6}\s|\Z)',
        '\n',
        cleaned,
        flags=re.IGNORECASE,
    )
    return cleaned


def extract_success_path(content: str) -> str | None:
    """Extract internal best-path summary for experience storage."""
    if not content:
        return None
    html_match = re.search(
        r'<p>\s*<strong>\s*最佳路径总结[:：]\s*</strong>\s*(?:<br\s*/?>)?([\s\S]*?)</p>',
        content,
        flags=re.IGNORECASE,
    )
    if html_match:
        text = re.sub(r'<br\s*/?>', '\n', html_match.group(1), flags=re.IGNORECASE)
        text = re.sub(r'<[^>]+>', '', text).strip()
        return text or None
    md_match = re.search(
        r'(?:^|\n)\s*(?:\*\*)?最佳路径总结[:：](?:\*\*)?\s*([\s\S]*?)(?=\n\s*📎\s*来源[:：]|\n\s*#{1,6}\s|\Z)',
        content,
        flags=re.IGNORECASE,
    )
    if md_match:
        text = re.sub(r'[*_`]+', '', md_match.group(1)).strip()
        return text or None
    return None


def _extract_source_block(content: str) -> tuple[str, str]:
    """Return content without source block plus the extracted source block."""
    html_match = re.search(
        r'<p>\s*📎\s*来源[:：]?\s*</p>\s*<ul>([\s\S]*?)</ul>',
        content,
        flags=re.IGNORECASE,
    )
    if html_match:
        return (content[:html_match.start()] + content[html_match.end():]).strip(), html_match.group(1)
    md_match = re.search(r'(?:^|\n)\s*📎\s*来源[:：]?\s*\n?([\s\S]*)$', content)
    if md_match:
        return content[:md_match.start()].strip(), md_match.group(1)
    return content, ""


def extract_inline_references(content: str) -> list[dict]:
    """Extract model-written source list for message footer references."""
    _, source_block = _extract_source_block(content)
    if not source_block:
        return []
    refs: list[dict] = []
    seen: set[str] = set()
    link_re = re.compile(
        r'\[([^\]]+)\]\((https?://[^\s)]+)\)|<a\s+[^>]*href=["\'](https?://[^"\']+)["\'][^>]*>(.*?)</a>',
        flags=re.IGNORECASE,
    )
    for match in link_re.finditer(source_block):
        title = re.sub(r'<[^>]+>', '', match.group(1) or match.group(4) or '').strip()
        url = (match.group(2) or match.group(3) or '').strip()
        key = url or title
        if not key or key in seen:
            continue
        seen.add(key)
        refs.append({"type": "web", "title": title or url, "source": title or url, "excerpt": "", "url": url or None})
    if refs:
        return refs
    plain = re.sub(r'<[^>]+>', '\n', source_block)
    for line in plain.splitlines():
        title = re.sub(r'^\s*[-*\d.)、]+\s*', '', line).strip()
        if not title or title in seen:
            continue
        seen.add(title)
        refs.append({"type": "source", "title": title, "source": title, "excerpt": ""})
    return refs[:6]


def strip_inline_source_block(content: str) -> str:
    """Remove model-written source block from user-visible content."""
    clean, _ = _extract_source_block(content)
    return clean


def _looks_like_unfinished_tool_intent(content: str) -> bool:
    """Detect if content makes a search/fetch promise without actual tool calls."""
    if not content:
        return False
    compact = "".join(content.split())
    if len(compact) > 160:
        return False
    return any(marker in compact for marker in _SEARCH_INTENT_MARKERS)


def process(content: str) -> ContentGateResult:
    """Process model output through ContentGate.

    Normalizes DSML, extracts inline tool calls, cleans XML markup,
    classifies the result, and returns a ContentGateResult.
    """
    result = ContentGateResult(content)

    if not content:
        result.is_empty = True
        result.blocked_reason = "empty_input"
        return result

    # Step 1: Normalize DSML/full-width markup
    normalized = _normalize_inline_markup(content)
    result.normalized_text = normalized

    # Step 2: Parse inline invoke tags (DSML inline tool calls)
    invoke_re = re.compile(
        r'<\w*:?invoke\s+name=["\']([^"\']+)["\']\s*>(.*?)</\w*:?invoke\s*>',
        re.IGNORECASE | re.DOTALL,
    )
    param_re = re.compile(
        r'<\w*:?parameter\s+name=["\']([^"\']+)["\']'
        r'(?:\s+string=["\'](true|false)["\'])?\s*>(.*?)</\w*:?parameter\s*>',
        re.IGNORECASE | re.DOTALL,
    )

    tool_calls: list[dict] = []
    for m in invoke_re.finditer(normalized):
        tool_name = m.group(1).strip()
        inner = m.group(2)
        args: dict = {}
        for pm in param_re.finditer(inner):
            pname = pm.group(1).strip()
            raw_val = pm.group(3).strip()
            string_hint = pm.group(2)
            if string_hint and string_hint.lower() == "false":
                try:
                    args[pname] = json.loads(raw_val)
                except (json.JSONDecodeError, TypeError):
                    args[pname] = raw_val
            else:
                args[pname] = raw_val
        tool_calls.append({
            "id": f"call_inline_{uuid.uuid4().hex[:12]}",
            "type": "function",
            "function": {"name": tool_name, "arguments": args},
        })

    result.inline_tool_calls = tool_calls
    result.extracted_tool_calls_count = len(tool_calls)

    # Step 3: Remove inline invoke tags and tool_call containers
    clean = invoke_re.sub('', normalized)
    clean = re.sub(
        r'<\w*:?invoke\s+name=.*?</\w*:?invoke\s*>',
        '', clean, flags=re.IGNORECASE | re.DOTALL,
    )
    clean = re.sub(
        r'<\w*:?tool_calls?\s*>.*?</\w*:?tool_calls?\s*>',
        '', clean, flags=re.IGNORECASE | re.DOTALL,
    )
    clean = _strip_tool_call_containers(clean)
    clean = _strip_internal_success_sections(clean)
    clean = strip_inline_source_block(clean)
    clean = re.sub(r'\n{3,}', '\n\n', clean).strip()

    result.clean_text = clean

    # Step 4: Classify
    has_visible = bool(clean)
    result.has_visible_text = has_visible
    result.is_empty = not has_visible

    if not has_visible and tool_calls:
        # All content was tool call markup - no user-visible text
        result.is_xml_only = True
        result.blocked_reason = "xml_only"

    if not has_visible and not tool_calls:
        result.blocked_reason = "cleaned_to_empty" if content.strip() else "cleaned_to_empty"

    # Step 5: Check for unfinished tool intent (promised search but no tool call)
    if has_visible and not tool_calls:
        if _looks_like_unfinished_tool_intent(clean):
            result.unfinished_tool_intent = True
            result.blocked_reason = "unfinished_tool_intent"

    return result


# ── Convenience re-exports for backward compatibility ──────────────────

def parse_inline_tool_calls(content: str) -> tuple[str, list[dict]]:
    """Backward-compatible wrapper around ContentGate.process()."""
    r = process(content)
    return r.clean_text, r.inline_tool_calls


def final_clean_content(content: str) -> str:
    """Backward-compatible wrapper: return only clean_text."""
    r = process(content)
    return r.clean_text


_MODEL_ERROR_MARKERS = (
    "model error",
    "all connection attempts failed",
    "connection refused",
    "connection reset",
    "connect timeout",
    "read timeout",
    "timeout",
    "httpx",
    "openai",
    "api key",
    "provider",
    "upstream",
    "stream error",
)


MODEL_UNAVAILABLE_MESSAGE = "模型服务暂时连接失败，请稍后重试。"


def user_safe_error_message(error: object) -> str:
    """Convert internal model/provider errors to a user-safe message."""
    text = str(error or "").strip()
    if not text:
        return "AI 助手暂时无法完成回复，请稍后重试。"
    lowered = text.lower()
    if any(marker in lowered for marker in _MODEL_ERROR_MARKERS):
        return MODEL_UNAVAILABLE_MESSAGE
    if len(text) > 120:
        return "AI 助手暂时无法完成回复，请稍后重试。"
    return text


def looks_like_unfinished_tool_intent(content: str) -> bool:
    """Backward-compatible wrapper."""
    return _looks_like_unfinished_tool_intent(content)
