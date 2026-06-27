"""Document export service for knowledge base.

Exports parsed documents in various formats: Markdown, HTML, JSON.
All exports consume the unified DocumentIr - no direct dependency on
parser internals or raw parser output.
"""
import json
import logging
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..ir_models import DocumentIr, from_legacy_blocks

logger = logging.getLogger("v2.knowledge").getChild("export")


async def export_document(
    db: AsyncSession,
    document_id: int,
    fmt: str = "markdown",
    owner_id: int | None = None,
) -> dict:
    """Export a parsed document in the specified format.

    fmt supports: "markdown", "html", "json"

    Returns: {"format": str, "content": str, "filename": str, "document_id": int}
    """
    from ..models import KbDocument

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
        select(KbChunk).where(
            KbChunk.document_id == document_id
        ).order_by(KbChunk.page, KbChunk.chunk_index)
    )
    chunks = cr.scalars().all()

    fusion_r = await db.execute(
        select(KbPageFusion).where(
            KbPageFusion.document_id == document_id
        ).order_by(KbPageFusion.page)
    )
    fusions = fusion_r.scalars().all()

    # Build DocumentIr from stored data
    ir_blocks = []
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

    if fusions:
        for pf in fusions:
            if pf.fused_text and pf.fused_text.strip():
                ir_blocks.append({
                    "type": "paragraph",
                    "text": pf.fused_text,
                    "page": pf.page,
                })

    doc_ir = from_legacy_blocks(
        file_id=doc.file_id,
        fmt=doc.extension or "unknown",
        blocks=ir_blocks,
    )

    base_filename = (doc.filename or f"document_{document_id}").rsplit(".", 1)[0]

    if fmt == "json":
        content = _export_json(doc_ir)
        filename = f"{base_filename}.json"
    elif fmt == "html":
        content = _export_html(doc_ir, doc.filename or f"Document {document_id}")
        filename = f"{base_filename}.html"
    else:
        content = _export_markdown(doc_ir)
        filename = f"{base_filename}.md"

    return {
        "format": fmt,
        "content": content,
        "filename": filename,
        "document_id": document_id,
        "success": True,
    }


def _export_markdown(doc_ir: DocumentIr) -> str:
    lines: list[str] = []
    lines.append(f"# 知识库导出 - {doc_ir.format}")
    lines.append(f"导出时间：{datetime.now().isoformat()}")
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


def _export_html(doc_ir: DocumentIr, title: str = "Document") -> str:
    parts: list[str] = []
    parts.append(f"<!DOCTYPE html><html><head><meta charset='utf-8'><title>{title}</title>")
    parts.append("<style>body{max-width:800px;margin:auto;padding:20px;font-family:sans-serif;line-height:1.6}")
    parts.append("h1,h2,h3{color:#333}table{border-collapse:collapse;width:100%}")
    parts.append("td,th{border:1px solid #ddd;padding:8px}code{background:#f4f4f4;padding:2px 4px}")
    parts.append("pre{background:#f4f4f4;padding:12px;overflow-x:auto}")
    parts.append("blockquote{border-left:3px solid #ccc;margin:0;padding:0 16px;color:#666}")
    parts.append("</style></head><body>")
    parts.append(f"<h1>{title}</h1>")
    parts.append(f"<p><em>导出时间：{datetime.now().isoformat()}</em></p>")

    for block in doc_ir.iter_non_empty():
        text = block.text.strip()
        if not text:
            continue
        if block.type == "heading":
            level = min(block.hierarchy_level or 1, 6)
            parts.append(f"<h{level}>{text}</h{level}>")
        elif block.type == "code":
            parts.append(f"<pre><code>{text}</code></pre>")
        elif block.type == "table":
            rows = text.split("\n")
            parts.append("<table>")
            for i, row in enumerate(rows):
                cells = row.split(" | ")
                tag = "th" if i == 0 else "td"
                parts.append(f"<tr>{''.join(f'<{tag}>{c}</{tag}>' for c in cells)}</tr>")
            parts.append("</table>")
        elif block.type == "image":
            parts.append(f'<figure><img src="image" alt="{text}"><figcaption>{text}</figcaption></figure>')
        elif block.type == "quote":
            parts.append(f"<blockquote><p>{'<br>'.join(text.split(chr(10)))}</p></blockquote>")
        else:
            for paragraph in text.split("\n\n"):
                parts.append(f"<p>{paragraph}</p>")

    parts.append("</body></html>")
    return "\n".join(parts)


def _export_json(doc_ir: DocumentIr) -> str:
    export_data = {
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
