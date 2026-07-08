import json
import logging
from urllib.parse import urlencode

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
        if not isinstance(r_item, dict):
            continue
        if not _looks_like_knowledge_result(r_item):
            continue
        doc_name = (
            r_item.get("document_name")
            or r_item.get("source_file")
            or r_item.get("filename", "")
        )
        file_id = r_item.get("file_id") or r_item.get("source_file_id")
        page = r_item.get("page")
        extension = _knowledge_result_extension(r_item, doc_name)
        excerpt = (r_item.get("text") or r_item.get("page_fusion", "") or "")[:240]
        title_parts = []
        if doc_name:
            title_parts.append(doc_name)
        if page is not None:
            title_parts.append(f"第{page}页")
        title = " ".join(title_parts) if title_parts else "知识库"
        open_url = ""
        if file_id:
            query = {
                "file_id": file_id,
                "file_name": doc_name or "",
                "format": extension,
            }
            if page is not None:
                query["page"] = page
            open_url = f"app://file/open?{urlencode(query)}"
        ref = {
            "type": "knowledge",
            "ref_key": "file_id" if file_id else "document_id",
            "ref_id": str(file_id or r_item.get("document_id") or ""),
            "title": title,
            "source": doc_name or "知识库",
            "source_module": "knowledge",
            "file_id": file_id,
            "source_file_id": file_id,
            "document_id": r_item.get("document_id"),
            "chunk_id": r_item.get("chunk_id"),
            "package_id": r_item.get("content_package_id") or r_item.get("package_id"),
            "page": page,
            "section": r_item.get("section"),
            "score": r_item.get("score"),
            "excerpt": excerpt,
            "download_url": f"/api/files/download/{file_id}" if file_id else "",
        }
        if extension:
            ref["format"] = extension
        if open_url:
            ref["open_url"] = open_url
            ref["url"] = open_url
        refs.append(ref)
    return refs


def _looks_like_knowledge_result(item: dict) -> bool:
    return any(
        item.get(key) is not None
        for key in (
            "file_id",
            "source_file_id",
            "document_id",
            "chunk_id",
            "content_package_id",
            "package_id",
            "document_name",
            "source_file",
            "filename",
            "page_fusion",
        )
    )


def _knowledge_result_extension(item: dict, doc_name: object) -> str:
    explicit = str(item.get("extension") or item.get("format") or "").strip().lower().lstrip(".")
    if explicit:
        return explicit
    for candidate in (item.get("source_file"), item.get("filename"), doc_name):
        name = str(candidate or "").strip()
        suffix = name.rsplit(".", 1)[-1].strip().lower() if "." in name else ""
        if suffix:
            return suffix
    return ""


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


_ARTIFACT_REF_LABELS = {
    "file_id": "文件",
    "package_id": "内容包",
    "artifact_id": "产物",
    "document_id": "文档",
    "chunk_id": "片段",
    "page": "页码",
    "source_file_id": "源文件",
}


def _artifact_ref_type(key: str) -> str:
    if key.endswith("_id"):
        return key[:-3].replace("_", "-")
    return key.replace("_", "-")


def artifact_refs_from_value(value: object, limit: int = 40) -> list[dict]:
    """Extract lightweight artifact/reference ids from tool outputs.

    The Agent module only preserves ids returned by tools. It does not read
    Content/Knowledge tables here.
    """
    refs: list[dict] = []
    seen: set[str] = set()

    def add_ref(key: str, raw_value: object, context: dict | None = None) -> None:
        if len(refs) >= limit:
            return
        if raw_value is None or isinstance(raw_value, (dict, list, tuple, set)):
            return
        ref_id = str(raw_value).strip()
        if not ref_id:
            return
        ref_type = _artifact_ref_type(key)
        dedupe_key = f"{ref_type}:{key}:{ref_id}"
        if dedupe_key in seen:
            return
        seen.add(dedupe_key)
        label = _ARTIFACT_REF_LABELS.get(key, key)
        item = {
            "type": ref_type,
            "title": f"{label} {ref_id}",
            "source": key,
            "excerpt": "",
            "ref_key": key,
            "ref_id": ref_id,
        }
        if isinstance(context, dict):
            for context_key in (
                "source_module",
                "file_id",
                "source_file_id",
                "document_id",
                "chunk_id",
                "package_id",
                "artifact_id",
                "page",
                "section",
                "score",
                "download_url",
                "open_url",
            ):
                context_value = context.get(context_key)
                if context_value is not None and context_key not in item:
                    item[context_key] = context_value
            snippet = context.get("snippet") or context.get("excerpt") or context.get("text")
            if snippet:
                item["excerpt"] = str(snippet)[:240]
            title = context.get("title") or context.get("document_name") or context.get("source_file")
            if title:
                item["title"] = str(title)
        item[key] = raw_value
        refs.append(item)

    def walk(node: object, depth: int = 0) -> None:
        if depth > 5 or len(refs) >= limit:
            return
        if isinstance(node, dict):
            for raw_key, child in node.items():
                key = str(raw_key)
                if key in _ARTIFACT_REF_LABELS:
                    add_ref(key, child, node)
                walk(child, depth + 1)
        elif isinstance(node, (list, tuple, set)):
            for child in list(node)[:50]:
                walk(child, depth + 1)

    walk(value)
    return refs


def _extend_unique_refs(target: list[dict], refs: list[dict]) -> None:
    seen = {
        ref.get("url") or f"{ref.get('type')}:{ref.get('ref_key') or ref.get('source')}:{ref.get('ref_id') or ref.get('title')}"
        for ref in target
    }
    for ref in refs:
        key = ref.get("url") or f"{ref.get('type')}:{ref.get('ref_key') or ref.get('source')}:{ref.get('ref_id') or ref.get('title')}"
        if key in seen:
            continue
        seen.add(key)
        target.append(ref)


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
        name = event.get("effective_tool_name") or event.get("name", "") or ""
        result = event.get("result", {}) or {}
        name, result = _unwrap_skill_result(name, result)
        has_knowledge_refs = False

        # Dispatch by tool name prefix
        extractor = _TOOL_EXTRACTORS.get(name)
        if extractor:
            extracted = extractor(result)
            if extracted:
                has_knowledge_refs = name == "knowledge__search"
                _extend_unique_refs(refs, extracted)

        # File-reading tools (matched by prefix)
        if name in ("desktop-tools__read_file",) or name.startswith("docs-open__") or name.startswith("terminal-tools__read_file"):
            extracted = _extract_file_refs(name, result)
            if extracted:
                _extend_unique_refs(refs, extracted)

        # Knowledge-related tools that return results in standard shape
        # (knowledge__get_block, knowledge__get_page_fusion, etc.)
        knowledge_refs = _extract_knowledge_refs(result)
        if knowledge_refs:
            has_knowledge_refs = True
            _extend_unique_refs(refs, knowledge_refs)

        if has_knowledge_refs:
            continue

        artifact_refs = artifact_refs_from_value(result)
        if artifact_refs:
            _extend_unique_refs(refs, artifact_refs)

    return refs
