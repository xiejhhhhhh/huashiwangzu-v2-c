"""Document export service for knowledge base.

Exports parsed documents in various formats: Markdown, HTML, JSON.
All exports consume the unified DocumentIr - no direct dependency on
parser internals or raw parser output.
"""
import json
import logging
from datetime import datetime
from html import escape

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..ir_models import DocumentIr, from_legacy_blocks

logger = logging.getLogger("v2.knowledge").getChild("export")
VALID_EXPORT_FORMATS = {"markdown", "html", "json"}


async def export_document(
    db: AsyncSession,
    document_id: int,
    fmt: str = "markdown",
    owner_id: int | None = None,
) -> dict:
    """Export a parsed document in the specified format."""
    from ..models import KbDocument

    normalized_fmt = (fmt or "markdown").lower().strip()
    if normalized_fmt not in VALID_EXPORT_FORMATS:
        return {
            "error": "Unsupported export format. Use markdown, html, or json.",
            "success": False,
        }

    query = select(KbDocument).where(KbDocument.id == document_id)
    if owner_id is not None:
        query = query.where(KbDocument.owner_id == owner_id)
    r = await db.execute(query)
    doc = r.scalar_one_or_none()
    if not doc:
        return {"error": "Document not found", "success": False}
    if doc.parse_status != "done":
        return {"error": f"Document not parsed (status: {doc.parse_status})", "success": False}

    from ..models import KbChunk, KbPageFusion

    cr = await db.execute(
        select(KbChunk).where(KbChunk.document_id == document_id)
        .order_by(KbChunk.page, KbChunk.chunk_index)
    )
    chunks = cr.scalars().all()
    if owner_id is not None:
        chunks = [chunk for chunk in chunks if chunk.owner_id == owner_id]

    fusion_r = await db.execute(
        select(KbPageFusion).where(KbPageFusion.document_id == document_id)
        .order_by(KbPageFusion.page)
    )
    fusions = fusion_r.scalars().all()
    if owner_id is not None:
        fusions = [fusion for fusion in fusions if fusion.owner_id == owner_id]

    ir_blocks = []
    export_source = "chunks"
    usable_fusions = [pf for pf in fusions if pf.fused_text and pf.fused_text.strip()]
    if usable_fusions:
        export_source = "page_fusion"
        for pf in fusions:
            if pf.fused_text and pf.fused_text.strip():
                ir_blocks.append({
                    "type": "paragraph",
                    "text": pf.fused_text,
                    "page": pf.page,
                })
    else:
        for ch in chunks:
            bt = ch.block_type
            if bt == "标题":
                block_type = "heading"
            elif bt == "表格":
                block_type = "table"
            elif bt == "图片":
                block_type = "image"
            elif bt == "代码":
                block_type = "code"
            else:
                block_type = "paragraph"
            ir_blocks.append({
                "type": block_type,
                "text": ch.text,
                "page": ch.page,
            })

    doc_ir = from_legacy_blocks(
        file_id=doc.file_id,
        fmt=doc.extension or "unknown",
        blocks=ir_blocks,
    )

    base_filename = (doc.filename or f"document_{document_id}").rsplit(".", 1)[0]
    metadata = {
        "document_id": document_id,
        "title": doc.filename or f"Document {document_id}",
        "format": normalized_fmt,
        "source_status": "available",
        "search_ready": doc.parse_status == "done" and doc.vector_status == "done" and (doc.total_chunks or 0) > 0,
        "deep_ready": doc.raw_status == "done" and doc.fusion_status == "done",
        "block_count": len(doc_ir.iter_non_empty()),
        "evidence_count": len(doc_ir.iter_non_empty()),
        "export_source": export_source,
    }

    if normalized_fmt == "json":
        content = _export_json(doc_ir, metadata)
        filename = f"{base_filename}.json"
    elif normalized_fmt == "html":
        content = _export_html(doc_ir, metadata)
        filename = f"{base_filename}.html"
    else:
        content = _export_markdown(doc_ir, metadata)
        filename = f"{base_filename}.md"

    return {
        "format": normalized_fmt,
        "content": content,
        "filename": filename,
        "document_id": document_id,
        "metadata": metadata,
        "success": True,
    }


def _export_markdown(doc_ir: DocumentIr, metadata: dict) -> str:
    lines: list[str] = []
    lines.append(f"# {metadata['title']}")
    lines.append(f"导出时间：{datetime.now().isoformat()}")
    lines.append(f"document_id：{metadata['document_id']}")
    lines.append(f"format：{metadata['format']}")
    lines.append(f"source_status：{metadata['source_status']}")
    lines.append(f"search_ready：{metadata['search_ready']}")
    lines.append(f"deep_ready：{metadata['deep_ready']}")
    lines.append(f"block_count：{metadata['block_count']}")
    lines.append(f"来源格式：{doc_ir.format}")
    lines.append("")

    for block in doc_ir.iter_non_empty():
        text = block.text.strip()
        if not text:
            continue
        if block.type == "heading":
            level = min(block.hierarchy_level or 1, 6)
            lines.append(f"{'#' * level} {text}")
        elif block.type == "code":
            lines.append("```")
            lines.append(text)
            lines.append("```")
        elif block.type == "table":
            lines.append(text)
        elif block.type == "image":
            lines.append(f"![{text}](image)")
        elif block.type == "quote":
            for line in text.split("\n"):
                lines.append(f"> {line}")
        else:
            lines.append(text)
        lines.append("")

    return "\n".join(lines)


def _export_html(doc_ir: DocumentIr, metadata: dict) -> str:
    title = str(metadata["title"])
    parts: list[str] = []
    parts.append(f"<!DOCTYPE html><html><head><meta charset='utf-8'><title>{escape(title)}</title>")
    parts.append("<style>body{max-width:800px;margin:auto;padding:20px;font-family:sans-serif;line-height:1.6}")
    parts.append("h1,h2,h3{color:#333}table{border-collapse:collapse;width:100%}")
    parts.append("td,th{border:1px solid #ddd;padding:8px}code{background:#f4f4f4;padding:2px 4px}")
    parts.append("pre{background:#f4f4f4;padding:12px;overflow-x:auto}")
    parts.append("blockquote{border-left:3px solid #ccc;margin:0;padding:0 16px;color:#666}")
    parts.append("</style></head><body>")
    parts.append(f"<h1>{escape(title)}</h1>")
    parts.append(f"<p><em>导出时间：{datetime.now().isoformat()}</em></p>")
    parts.append("<dl>")
    for key in ("document_id", "format", "source_status", "search_ready", "deep_ready", "block_count"):
        parts.append(f"<dt>{escape(str(key))}</dt><dd>{escape(str(metadata[key]))}</dd>")
    parts.append("</dl>")

    for block in doc_ir.iter_non_empty():
        text = block.text.strip()
        if not text:
            continue
        if block.type == "heading":
            level = min(block.hierarchy_level or 1, 6)
            parts.append(f"<h{level}>{escape(text)}</h{level}>")
        elif block.type == "code":
            parts.append(f"<pre><code>{escape(text)}</code></pre>")
        elif block.type == "table":
            rows = text.split("\n")
            parts.append("<table>")
            for i, row in enumerate(rows):
                cells = row.split(" | ")
                tag = "th" if i == 0 else "td"
                parts.append(f"<tr>{''.join(f'<{tag}>{escape(c)}</{tag}>' for c in cells)}</tr>")
            parts.append("</table>")
        elif block.type == "image":
            safe_text = escape(text)
            parts.append(f'<figure><img src="image" alt="{safe_text}"><figcaption>{safe_text}</figcaption></figure>')
        elif block.type == "quote":
            parts.append(f"<blockquote><p>{'<br>'.join(escape(text).split(chr(10)))}</p></blockquote>")
        else:
            for paragraph in text.split("\n\n"):
                parts.append(f"<p>{escape(paragraph)}</p>")

    parts.append("</body></html>")
    return "\n".join(parts)


def _export_json(doc_ir: DocumentIr, metadata: dict) -> str:
    export_data = {
        "metadata": metadata,
        "format": doc_ir.format,
        "total_blocks": len(doc_ir.blocks),
        "exported_at": datetime.now().isoformat(),
        "blocks": [
            {
                "type": b.type,
                "text": b.text,
                "page": b.page,
                "hierarchy_level": b.hierarchy_level,
            }
            for b in doc_ir.iter_non_empty()
        ],
        "resources": [
            {
                "id": r.id,
                "type": r.type,
                "text_desc": r.text_desc,
            }
            for r in doc_ir.resources
        ],
    }
    return json.dumps(export_data, ensure_ascii=False, indent=2)
