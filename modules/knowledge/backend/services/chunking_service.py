"""Advanced chunking strategies for knowledge base.

Replaces the basic fixed-size chunking with title-aware and structure-aware
strategies that respect document semantics. All strategies consume DocumentIr
and produce chunks compatible with kb_chunks storage.

Strategies:
- title_aware: Split on heading boundaries, keep related content under each heading
- structure_aware: Follow the DocumentIr hierarchy, respect block types
- fixed_size: Legacy paragraph/sentence-based splitting (backward compat)
"""
import logging
import re
from typing import Literal

from ..ir_models import ContentBlock, DocumentIr

logger = logging.getLogger("v2.knowledge").getChild("chunking")

ChunkStrategy = Literal["title_aware", "structure_aware", "fixed_size"]

# Chunk size parameters
MAX_CHUNK_CHARS = 512
MIN_CHUNK_CHARS = 100
OVERLAP_CHARS = 50


def chunk_document(
    doc_ir: DocumentIr,
    strategy: ChunkStrategy = "title_aware",
    max_chars: int = MAX_CHUNK_CHARS,
    overlap: int = OVERLAP_CHARS,
) -> list[dict]:
    """Chunk a DocumentIr using the specified strategy.

    Returns list of chunk dicts compatible with kb_chunks store_chunks format:
    [{"block_type": str, "text": str, "page": int|null, "chunk_index": int,
      "heading": str|null, "hierarchy_level": int}, ...]
    """
    if strategy == "title_aware":
        return _chunk_title_aware(doc_ir, max_chars, overlap)
    elif strategy == "structure_aware":
        return _chunk_structure_aware(doc_ir, max_chars, overlap)
    else:
        return _chunk_fixed_size(doc_ir, max_chars, overlap)


def _chunk_title_aware(
    doc_ir: DocumentIr,
    max_chars: int = MAX_CHUNK_CHARS,
    overlap: int = OVERLAP_CHARS,
) -> list[dict]:
    """Title-aware chunking: split on heading boundaries.

    Each heading block starts a new section. Content under a heading is kept
    together until the next heading at the same or higher level. Sections
    that exceed max_chars are further split by sub-headings or paragraphs.
    """
    blocks = doc_ir.iter_non_empty()
    if not blocks:
        return []

    sections: list[dict] = []
    current_section: list[ContentBlock] = []
    current_heading: str | None = None
    current_level: int = 0

    for block in blocks:
        if block.type == "heading":
            if current_section:
                sections.append({
                    "heading": current_heading,
                    "level": current_level,
                    "blocks": current_section,
                })
            current_heading = block.text
            current_level = block.hierarchy_level or 1
            current_section = []
        else:
            current_section.append(block)

    if current_section:
        sections.append({
            "heading": current_heading,
            "level": current_level,
            "blocks": current_section,
        })

    chunks: list[dict] = []
    chunk_index = 0

    for sec in sections:
        heading = sec["heading"]
        level = sec["level"]
        sec_blocks = sec["blocks"]

        if not sec_blocks:
            continue

        section_text = "\n\n".join(b.text for b in sec_blocks if b.text.strip())
        if not section_text.strip():
            continue

        if heading:
            combined = f"{heading}\n\n{section_text}"
        else:
            combined = section_text

        if len(combined) <= max_chars:
            chunks.append({
                "block_type": "段落",
                "text": combined,
                "page": sec_blocks[0].page,
                "chunk_index": chunk_index,
                "heading": heading,
                "hierarchy_level": level,
            })
            chunk_index += 1
        else:
            sub_chunks = _split_text(combined, max_chars, overlap)
            for sub_text in sub_chunks:
                if not sub_text.strip():
                    continue
                chunks.append({
                    "block_type": "段落",
                    "text": sub_text,
                    "page": sec_blocks[0].page,
                    "chunk_index": chunk_index,
                    "heading": heading,
                    "hierarchy_level": level,
                })
                chunk_index += 1

    logger.info("Title-aware chunking: %d chunks from %d sections", len(chunks), len(sections))
    return chunks


def _chunk_structure_aware(
    doc_ir: DocumentIr,
    max_chars: int = MAX_CHUNK_CHARS,
    overlap: int = OVERLAP_CHARS,
) -> list[dict]:
    """Structure-aware chunking: follow DocumentIr hierarchy.

    Each top-level block is a chunk candidate. Tables and code blocks
    are kept intact (not split). Headings start new chunks.
    Paragraphs under the same heading are grouped.
    """
    chunks: list[dict] = []
    chunk_index = 0
    current_chunk_text = ""
    current_heading: str | None = None
    current_hierarchy = 0
    current_page: int | None = None

    def flush():
        nonlocal current_chunk_text
        if current_chunk_text.strip():
            chunks.append({
                "block_type": "段落",
                "text": current_chunk_text.strip(),
                "page": current_page,
                "chunk_index": chunk_index,
                "heading": current_heading,
                "hierarchy_level": current_hierarchy,
            })
            nonlocal chunk_index
            chunk_index += 1
        current_chunk_text = ""

    for block in doc_ir.iter_non_empty():
        text = block.text.strip()
        if not text:
            continue

        if block.type == "heading":
            flush()
            current_heading = block.text
            current_hierarchy = block.hierarchy_level or 1
            current_chunk_text = text
        elif block.type in ("table", "code"):
            flush()
            chunks.append({
                "block_type": block.type,
                "text": text,
                "page": block.page,
                "chunk_index": chunk_index,
                "heading": current_heading,
                "hierarchy_level": current_hierarchy,
            })
            chunk_index += 1
        elif block.type == "image":
            if text:
                flush()
                chunks.append({
                    "block_type": "图片",
                    "text": text,
                    "page": block.page,
                    "chunk_index": chunk_index,
                    "heading": current_heading,
                    "hierarchy_level": current_hierarchy,
                })
                chunk_index += 1
        else:
            if len(current_chunk_text) + len(text) + 1 > max_chars and current_chunk_text:
                flush()
                current_chunk_text = text
            else:
                if current_chunk_text:
                    current_chunk_text += "\n\n" + text
                else:
                    current_chunk_text = text
            current_page = block.page

    flush()
    logger.info("Structure-aware chunking: %d chunks", len(chunks))
    return chunks


def _chunk_fixed_size(
    doc_ir: DocumentIr,
    max_chars: int = MAX_CHUNK_CHARS,
    overlap: int = OVERLAP_CHARS,
) -> list[dict]:
    """Fixed-size chunking (backward compat).

    Splits text by paragraphs first, then sentences, then hard cut.
    """
    from .embedding_service import split_text_into_chunks

    chunks: list[dict] = []
    chunk_index = 0

    for block in doc_ir.iter_non_empty():
        text = block.text.strip()
        if not text:
            continue
        sub_chunks = split_text_into_chunks(text, max_chars, overlap)
        for sub_text in sub_chunks:
            if not sub_text.strip():
                continue
            chunks.append({
                "block_type": "段落",
                "text": sub_text,
                "page": block.page,
                "chunk_index": chunk_index,
                "heading": None,
                "hierarchy_level": 0,
            })
            chunk_index += 1

    return chunks


def _split_text(text: str, max_chars: int, overlap: int) -> list[str]:
    if not text or not text.strip():
        return []
    text = text.strip()
    if len(text) <= max_chars:
        return [text]

    chunks: list[str] = []
    paragraphs = re.split(r"\n\s*\n", text)
    current = ""

    for para in paragraphs:
        para = para.strip()
        if not para:
            continue
        if len(para) > max_chars:
            if current:
                chunks.append(current)
                current = ""
            sentences = re.split(r"(?<=[。！？.!?])\s*", para)
            for sent in sentences:
                sent = sent.strip()
                if not sent:
                    continue
                if len(sent) > max_chars:
                    if current:
                        chunks.append(current)
                        current = ""
                    for i in range(0, len(sent), max_chars - overlap):
                        segment = sent[i:i + max_chars]
                        if segment:
                            chunks.append(segment)
                else:
                    if len(current) + len(sent) + 1 > max_chars:
                        chunks.append(current)
                        current = sent
                    else:
                        current = (current + " " + sent) if current else sent
        else:
            if len(current) + len(para) + 1 > max_chars:
                chunks.append(current)
                current = para
            else:
                current = (current + "\n\n" + para) if current else para

    if current:
        chunks.append(current)

    return chunks
