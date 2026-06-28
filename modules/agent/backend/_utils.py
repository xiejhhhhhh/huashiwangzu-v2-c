import json
import logging

logger = logging.getLogger("v2.agent").getChild("_utils")


def j(obj) -> str:
    return json.dumps(obj, ensure_ascii=False, default=str)


def tool_calls_for_history(tool_calls: list[dict]) -> list[dict]:
    normalized = []
    for item in tool_calls:
        fn = item.get("function", item)
        args = fn.get("arguments") or {}
        if not isinstance(args, str):
            args = j(args)
        normalized.append({
            "id": item.get("id", ""),
            "type": item.get("type", "function"),
            "function": {
                "name": fn.get("name", ""),
                "arguments": args,
            },
        })
    return normalized


def _extract_web_search_refs(result: dict) -> list[dict]:
    """Extract references from web-tools__search results."""
    refs: list[dict] = []
    results_list = result.get("results") if isinstance(result, dict) else []
    if not isinstance(results_list, list):
        return refs
    for r in results_list:
        if not isinstance(r, dict):
            continue
        title = r.get("title") or ""
        url = r.get("url") or ""
        snippet = r.get("snippet") or ""
        if not title and not url:
            continue
        refs.append({
            "type": "web",
            "title": title or url,
            "url": url,
            "source": url,
            "excerpt": snippet[:240] if snippet else "",
        })
    return refs


def _extract_web_fetch_refs(result: dict) -> list[dict]:
    """Extract references from web-tools__fetch results."""
    if not isinstance(result, dict):
        return []
    title = result.get("title") or ""
    url = result.get("url") or ""
    text = result.get("text") or ""
    if not url:
        return []
    return [{
        "type": "web",
        "title": title or url,
        "url": url,
        "source": url,
        "excerpt": text[:240],
    }]


def _extract_knowledge_refs(result: dict) -> list[dict]:
    """Extract references from knowledge__search results."""
    refs: list[dict] = []
    inner = result.get("data", result) if isinstance(result, dict) else {}
    results_list = inner.get("results", []) if isinstance(inner, dict) else []
    if not isinstance(results_list, list):
        return refs
    for r_item in results_list:
        doc_name = r_item.get("document_name") or r_item.get("filename", "")
        page = r_item.get("page")
        excerpt = (r_item.get("text") or r_item.get("page_fusion", "") or "")[:240]
        title_parts = []
        if doc_name:
            title_parts.append(doc_name)
        if page is not None:
            title_parts.append(f"第{page}页")
        title = " ".join(title_parts) if title_parts else "知识库"
        refs.append({
            "type": "knowledge",
            "title": title,
            "source": doc_name or "知识库",
            "excerpt": excerpt,
        })
    return refs


def _extract_file_refs(name: str, result: dict) -> list[dict]:
    """Extract references from file-reading tools (desktop-tools, docs-open, terminal-tools)."""
    if not isinstance(result, dict):
        return []
    # desktop-tools__read_file
    file_info = result.get("file")
    if isinstance(file_info, dict):
        filename = file_info.get("name") or ""
        if filename:
            return [{"type": "file", "title": filename, "source": filename, "excerpt": ""}]

    # docs-open results
    title = result.get("title") or ""
    if title:
        return [{"type": "file", "title": title, "source": title, "excerpt": ""}]

    # terminal-tools__read_file
    path = result.get("path") or ""
    if path:
        name_only = path.rsplit("/", 1)[-1]
        return [{"type": "file", "title": name_only, "source": path, "excerpt": ""}]

    return []


def _unwrap_skill_result(name: str, result: dict) -> tuple[str, dict]:
    if name != "skill_use" or not isinstance(result, dict):
        return name, result
    inner_name = result.get("name") or result.get("skill_name") or result.get("tool_name") or ""
    inner_result = result.get("result") or result.get("data") or result.get("output") or {}
    if isinstance(inner_result, dict) and inner_name:
        return str(inner_name), inner_result
    return name, result


# ── Tool-to-extractor dispatch table ───────────────────────────────
_TOOL_EXTRACTORS: dict[str, callable] = {
    "web-tools__search": _extract_web_search_refs,
    "web-tools__fetch": _extract_web_fetch_refs,
    "knowledge__search": _extract_knowledge_refs,
}


def references_from_tool_events(events: list[dict]) -> list[dict]:
    refs: list[dict] = []
    for event in events:
        if event.get("type") != "tool_result":
            continue
        name = event.get("name", "") or ""
        result = event.get("result", {}) or {}
        name, result = _unwrap_skill_result(name, result)

        # Dispatch by tool name prefix
        extractor = _TOOL_EXTRACTORS.get(name)
        if extractor:
            extracted = extractor(result)
            if extracted:
                refs.extend(extracted)
                continue

        # File-reading tools (matched by prefix)
        if name in ("desktop-tools__read_file",) or name.startswith("docs-open__") or name.startswith("terminal-tools__read_file"):
            extracted = _extract_file_refs(name, result)
            if extracted:
                refs.extend(extracted)
                continue

        # Knowledge-related tools that return results in standard shape
        # (knowledge__get_block, knowledge__get_page_fusion, etc.)
        knowledge_refs = _extract_knowledge_refs(result)
        if knowledge_refs:
            refs.extend(knowledge_refs)
            continue

    return refs
