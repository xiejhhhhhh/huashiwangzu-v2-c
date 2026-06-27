"""知识库分块与向量化服务。"""
import json
import logging
import re
from typing import AsyncIterator

from sqlalchemy import select, func, and_
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import AsyncSessionLocal
from app.services.model_services import get_embedding

logger = logging.getLogger("v2.knowledge").getChild("embedding")

# 分块参数
MAX_CHUNK_CHARS = 512       # 每块最大字符数
MIN_CHUNK_CHARS = 100       # 最小分块阈值（小于此值合并到前一块）
OVERLAP_CHARS = 50          # 块间重叠字符数


def split_text_into_chunks(text: str, max_chars: int = MAX_CHUNK_CHARS, overlap: int = OVERLAP_CHARS) -> list[str]:
    """将长文本按段落边界分割成块。

    策略：优先按段落（连续换行）分割 → 段太长则按句子（。！？\n）分割 → 再长则硬切。
    """
    if not text or not text.strip():
        return []
    text = text.strip()
    if len(text) <= max_chars:
        return [text]

    chunks: list[str] = []
    # 按段落分割（连续换行符）
    paragraphs = re.split(r"\n\s*\n", text)
    current = ""

    for para in paragraphs:
        para = para.strip()
        if not para:
            continue
        if len(para) > max_chars:
            # 长段落 → 按句子分割
            if current:
                chunks.append(current)
                current = ""
            sentences = re.split(r"(?<=[。！？.!?])\s*", para)
            for sent in sentences:
                sent = sent.strip()
                if not sent:
                    continue
                if len(sent) > max_chars:
                    # 超长句子 → 硬切
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


def extract_keywords(text: str, max_keywords: int = 10) -> str:
    """简单关键词提取：按词频取高频词（不含停用词）。

    中文处理：按单字/双字词频统计（简单实现，够用）。
    """
    if not text:
        return ""
    # 简单停用词
    stop_words = {
        "的", "了", "在", "是", "我", "有", "和", "就", "不", "人", "都", "一",
        "一个", "上", "也", "很", "到", "说", "要", "去", "你", "会", "着",
        "没有", "看", "好", "自己", "这", "他", "她", "它", "们", "那", "些",
        "之", "为", "与", "及", "但", "或", "被", "把", "从", "以", "而",
        "the", "a", "an", "is", "are", "was", "were", "be", "been", "being",
        "have", "has", "had", "do", "does", "did", "will", "would", "can",
        "could", "shall", "should", "may", "might", "must", "to", "of",
        "in", "for", "on", "with", "at", "by", "from", "as", "into",
        "this", "that", "these", "those", "it", "its", "and", "but", "or",
    }

    # 提取双字词 + 单字
    words: dict[str, int] = {}
    # 双字词
    for i in range(len(text) - 1):
        bigram = text[i:i + 2]
        if bigram.isalpha() and bigram.lower() not in stop_words and len(bigram.strip()) >= 2:
            words[bigram] = words.get(bigram, 0) + 1
    # 英文单词
    for match in re.finditer(r"[a-zA-Z]{3,}", text):
        w = match.group().lower()
        if w not in stop_words:
            words[w] = words.get(w, 0) + 1

    sorted_words = sorted(words.items(), key=lambda x: -x[1])
    return ", ".join(w for w, _ in sorted_words[:max_keywords])


async def chunk_and_embed(
    document_id: int,
    owner_id: int,
    blocks: list[dict],
    caller: str,
) -> list[dict]:
    """将解析块分块 + 向量化，返回待入库的 chunk 记录列表。

    blocks: [{"type": str, "text": str, "page": int|null, "resource_ref": int|null}, ...]
    返回: [{"document_id": int, "owner_id": int, "page": int, "chunk_index": int,
            "block_type": str, "text": str, "embedding": list[float], "keywords": str}, ...]
    """
    chunks_to_store: list[dict] = []
    chunk_index = 0

    for block in blocks:
        text = (block.get("text") or "").strip()
        if not text:
            continue
        block_type = block.get("type", "段落")
        page = block.get("page")

        sub_chunks = split_text_into_chunks(text)
        for sub_text in sub_chunks:
            if not sub_text.strip():
                continue
            ch = {
                "document_id": document_id,
                "owner_id": owner_id,
                "page": page,
                "chunk_index": chunk_index,
                "block_type": block_type,
                "text": sub_text,
                "embedding": None,
                "keywords": extract_keywords(sub_text),
            }
            chunks_to_store.append(ch)
            chunk_index += 1

    logger.info("Chunked document_id=%d into %d chunks", document_id, len(chunks_to_store))

    # 批量向量化（每批 5 个，避免请求超时）
    batch_size = 5
    total = len(chunks_to_store)
    for i in range(0, total, batch_size):
        batch = chunks_to_store[i:i + batch_size]
        texts = [ch["text"] for ch in batch]
        try:
            embeddings = []
            for text in texts:
                emb = await get_embedding(text)
                embeddings.append(emb)
            for j, emb in enumerate(embeddings):
                if i + j < total:
                    chunks_to_store[i + j]["embedding"] = emb
        except Exception as e:
            logger.warning("Embedding batch %d failed (non-fatal): %s", i // batch_size, e)
            # 向量化失败的块 embedding 为 None，不影响后续检索（纯文本检索仍可用）

        if (i + batch_size) % 20 == 0 or i + batch_size >= total:
            logger.info("Embedding progress: %d/%d chunks", min(i + batch_size, total), total)

    return chunks_to_store


async def store_chunks(db: AsyncSession, chunks: list[dict]) -> int:
    """批量写入 kb_chunks。返回写入条数。"""
    from ..models import KbChunk

    stored = 0
    for ch in chunks:
        record = KbChunk(
            document_id=ch["document_id"],
            owner_id=ch["owner_id"],
            page=ch["page"],
            chunk_index=ch["chunk_index"],
            block_type=ch["block_type"],
            text=ch["text"],
            embedding=ch.get("embedding"),
            keywords=ch.get("keywords"),
        )
        db.add(record)
        stored += 1
        # 每 50 条 flush 一次
        if stored % 50 == 0:
            await db.flush()
    await db.commit()
    logger.info("Stored %d chunks to kb_chunks", stored)
    return stored


async def get_chunk_by_id(db: AsyncSession, chunk_id: int) -> dict | None:
    """按 chunk_id 获取内容块详情。"""
    from ..models import KbChunk

    r = await db.execute(select(KbChunk).where(KbChunk.id == chunk_id))
    chunk = r.scalar_one_or_none()
    if not chunk:
        return None
    return {
        "id": chunk.id,
        "document_id": chunk.document_id,
        "page": chunk.page,
        "chunk_index": chunk.chunk_index,
        "block_type": chunk.block_type,
        "text": chunk.text,
        "keywords": chunk.keywords,
    }
